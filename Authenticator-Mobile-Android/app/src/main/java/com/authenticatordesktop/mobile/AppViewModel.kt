package com.authenticatordesktop.mobile

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.isActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class AppState(
    val loading: Boolean = true,
    val setupRequired: Boolean = false,
    val locked: Boolean = true,
    val privacyShield: Boolean = false,
    val snapshot: VaultSnapshot = VaultSnapshot(),
    val accountQuery: String = "",
    val passwordQuery: String = "",
    val accountGroup: String = "",
    val passwordGroup: String = "",
    val accountFavoriteOnly: Boolean = false,
    val passwordFavoriteOnly: Boolean = false,
    val accountShowPinned: Boolean = true,
    val passwordShowPinned: Boolean = true,
    val accountProviderKey: String = "",
    val accountOtherProvidersOnly: Boolean = false,
    val selectedAccountIds: Set<String> = emptySet(),
    val selectedPasswordIds: Set<String> = emptySet(),
    val accountSort: AccountSortPreference = AccountSortPreference(),
    val passwordSort: PasswordSortPreference = PasswordSortPreference(),
    val serverTerminalSessions: List<AndroidTerminalSession> = emptyList(),
)

sealed interface AppEvent {
    data class Message(val value: String) : AppEvent
    data class Error(val value: String) : AppEvent
}

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val gateway = PythonGateway(application)
    private val preferences = application.getSharedPreferences("mobile-settings", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(
        AppState(
            accountSort = AccountSortPreference(
                AccountSortField.fromValue(preferences.getString("account_sort_field", null)),
                MobileSortDirection.fromValue(preferences.getString("account_sort_direction", null)),
            ),
            passwordSort = PasswordSortPreference(
                PasswordSortField.fromValue(preferences.getString("password_sort_field", null)),
                MobileSortDirection.fromValue(preferences.getString("password_sort_direction", null)),
            ),
            accountShowPinned = preferences.getBoolean("account_show_pinned", true),
            passwordShowPinned = preferences.getBoolean("password_show_pinned", true),
        ),
    )
    val state = _state.asStateFlow()
    private val _events = MutableSharedFlow<AppEvent>(extraBufferCapacity = 8)
    val events = _events.asSharedFlow()
    private val gatewayMutex = Mutex()
    private val sshSessions = AndroidSshSessionManager()
    private var ticker: Job? = null
    private var searchRefresh: Job? = null
    private var backgroundAt = 0L

    init {
        viewModelScope.launch {
            sshSessions.sessions.collect { sessions ->
                _state.value = _state.value.copy(
                    serverTerminalSessions = sessions.values.sortedBy { it.id },
                )
            }
        }
        startup()
    }

    private fun startup() = viewModelScope.launch {
        runBusy {
            val result = JSONObject(invokeGateway { gateway.startup() })
            val setup = result.optString("status") == "needs_setup"
            _state.value = _state.value.copy(
                loading = false,
                setupRequired = setup,
                locked = !result.optBoolean("unlocked"),
            )
            if (result.optBoolean("unlocked")) refreshNow()
        }
    }

    private suspend fun runBusy(block: suspend () -> Unit) {
        try {
            block()
        } catch (error: Exception) {
            _state.value = _state.value.copy(loading = false)
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "操作失败"))
        }
    }

    private suspend fun <T> invokeGateway(action: () -> T): T =
        withContext(Dispatchers.IO) { gatewayMutex.withLock { action() } }

    fun initialize(password: String) = mutate("保险库已创建") { gateway.initialize(password) }
    fun unlock(password: String) = mutate("保险库已解锁") { gateway.unlock(password) }

    fun lock(message: String = "保险库已锁定") = viewModelScope.launch {
        runBusy {
            sshSessions.clearAll()
            invokeGateway { gateway.lock() }
            ticker?.cancel()
            searchRefresh?.cancel()
            _state.value = _state.value.copy(
                locked = true,
                snapshot = VaultSnapshot(),
                privacyShield = false,
                selectedAccountIds = emptySet(),
                selectedPasswordIds = emptySet(),
                serverTerminalSessions = emptyList(),
            )
            _events.emit(AppEvent.Message(message))
        }
    }

    fun changeMasterPassword(current: String, next: String) =
        mutate("主密码已修改") { gateway.changeMasterPassword(current, next) }

    fun setAccountQuery(value: String) {
        _state.value = _state.value.copy(accountQuery = value, selectedAccountIds = emptySet())
        scheduleSearchRefresh()
    }
    fun setPasswordQuery(value: String) {
        _state.value = _state.value.copy(passwordQuery = value, selectedPasswordIds = emptySet())
        scheduleSearchRefresh()
    }
    fun setAccountGroup(value: String) { _state.value = _state.value.copy(accountGroup = value, selectedAccountIds = emptySet()); refresh() }
    fun setPasswordGroup(value: String) { _state.value = _state.value.copy(passwordGroup = value, selectedPasswordIds = emptySet()); refresh() }
    fun setAccountFavoriteOnly(value: Boolean) { _state.value = _state.value.copy(accountFavoriteOnly = value, selectedAccountIds = emptySet()); refresh() }
    fun setPasswordFavoriteOnly(value: Boolean) { _state.value = _state.value.copy(passwordFavoriteOnly = value, selectedPasswordIds = emptySet()); refresh() }
    fun setAccountShowPinned(value: Boolean) {
        preferences.edit().putBoolean("account_show_pinned", value).apply()
        _state.value = _state.value.copy(accountShowPinned = value, selectedAccountIds = emptySet())
        refresh()
    }
    fun setAccountProvider(key: String) {
        val state = _state.value
        val nextKey = if (!state.accountOtherProvidersOnly && state.accountProviderKey == key) "" else key
        _state.value = state.copy(
            accountProviderKey = nextKey,
            accountOtherProvidersOnly = false,
            selectedAccountIds = emptySet(),
        )
        refresh()
    }
    fun setOtherAccountProvidersOnly() {
        val state = _state.value
        _state.value = state.copy(
            accountProviderKey = "",
            accountOtherProvidersOnly = !state.accountOtherProvidersOnly,
            selectedAccountIds = emptySet(),
        )
        refresh()
    }
    fun setPasswordShowPinned(value: Boolean) {
        preferences.edit().putBoolean("password_show_pinned", value).apply()
        _state.value = _state.value.copy(passwordShowPinned = value, selectedPasswordIds = emptySet())
        refresh()
    }

    private fun scheduleSearchRefresh() {
        searchRefresh?.cancel()
        searchRefresh = viewModelScope.launch {
            delay(220)
            runBusy { refreshNow() }
        }
    }

    fun refresh() = viewModelScope.launch { runBusy { refreshNow() } }

    private suspend fun refreshNow() {
        if (_state.value.locked) return
        val state = _state.value
        var resolvedState = state
        var snapshot = loadSnapshot(resolvedState)
        if (
            resolvedState.accountProviderKey.isNotBlank() &&
            snapshot.accountProviders.none { it.key == resolvedState.accountProviderKey }
        ) {
            resolvedState = resolvedState.copy(accountProviderKey = "")
            snapshot = loadSnapshot(resolvedState)
        } else if (
            resolvedState.accountOtherProvidersOnly && snapshot.otherProviderCount == 0
        ) {
            resolvedState = resolvedState.copy(accountOtherProvidersOnly = false)
            snapshot = loadSnapshot(resolvedState)
        }
        _state.value = resolvedState.copy(
            loading = false,
            locked = false,
            setupRequired = false,
            snapshot = snapshot,
        )
        if (ticker == null || ticker?.isActive != true) startTicker()
    }

    private suspend fun loadSnapshot(state: AppState): VaultSnapshot = parseSnapshot(
        invokeGateway {
            gateway.snapshot(
                state.accountQuery,
                state.passwordQuery,
                state.accountGroup,
                state.passwordGroup,
                state.accountFavoriteOnly,
                state.passwordFavoriteOnly,
                state.accountShowPinned,
                state.passwordShowPinned,
                state.accountSort,
                state.passwordSort,
                state.accountProviderKey,
                state.accountOtherProvidersOnly,
            )
        },
    )

    private fun startTicker() {
        ticker?.cancel()
        ticker = viewModelScope.launch {
            delay((1_000L - System.currentTimeMillis() % 1_000L).coerceAtLeast(1L))
            while (isActive) {
                runBusy { refreshDynamicOtpValues() }
                delay(1_000)
            }
        }
    }

    private suspend fun refreshDynamicOtpValues() {
        if (_state.value.locked) return
        val (locked, values) = parseOtpDynamicValues(invokeGateway { gateway.otpDynamicValues() })
        if (locked) {
            ticker?.cancel()
            _state.value = _state.value.copy(locked = true, snapshot = VaultSnapshot())
        } else if (values.isNotEmpty()) {
            _state.value = _state.value.copy(snapshot = _state.value.snapshot.withOtpDynamicValues(values))
        }
    }

    private fun mutate(message: String, action: () -> String) = viewModelScope.launch {
        runBusy {
            invokeGateway(action)
            _state.value = _state.value.copy(locked = false, setupRequired = false)
            refreshNow()
            _events.emit(AppEvent.Message(message))
        }
    }

    fun createAccount(data: JSONObject) = mutate("账号已添加") { gateway.createAccount(data.toString()) }
    fun updateAccount(data: JSONObject) = mutate("账号已更新") { gateway.updateAccount(data.toString()) }
    fun deleteAccount(id: String) = mutate("账号已删除") { gateway.deleteAccounts(JSONArray().put(id).toString()) }
    fun toggleAccountPinned(id: String) = mutate("置顶状态已更新") { gateway.toggleAccountPinned(id) }
    fun setAccountFavorite(id: String, value: Boolean) = mutate("收藏状态已更新") {
        gateway.setAccountFavorite(JSONArray().put(id).toString(), value)
    }
    fun incrementHotp(id: String) = mutate("已生成下一个 HOTP") { gateway.incrementHotp(id) }
    fun createGroup(name: String) = mutate("分组已创建") { gateway.createGroup(name) }
    fun renameGroup(id: String, name: String) = mutate("分组已重命名") { gateway.renameGroup(id, name) }
    fun deleteGroup(id: String) = mutate("分组已删除") { gateway.deleteGroup(id) }
    fun assignAccountGroups(id: String, groups: List<String>) = mutate("账号分组已更新") {
        gateway.assignAccountGroups(JSONArray().put(id).toString(), JSONArray(groups).toString())
    }

    fun createPassword(data: JSONObject) = mutate("密码记录已添加") { gateway.createPassword(data.toString()) }
    fun updatePassword(id: String, data: JSONObject) = mutate("密码记录已更新") { gateway.updatePassword(id, data.toString()) }
    fun deletePassword(id: String) = mutate("密码记录已删除") { gateway.deletePasswords(JSONArray().put(id).toString()) }
    fun togglePasswordPinned(item: PasswordRow) = mutate("置顶状态已更新") {
        gateway.setPasswordPinned(JSONArray().put(item.id).toString(), !item.pinned)
    }
    fun setPasswordFavorite(item: PasswordRow, value: Boolean) = mutate("收藏状态已更新") {
        gateway.setPasswordFavorite(JSONArray().put(item.id).toString(), value)
    }

    fun toggleAccountSelection(id: String) {
        val selected = _state.value.selectedAccountIds
        _state.value = _state.value.copy(
            selectedAccountIds = if (id in selected) selected - id else selected + id,
        )
    }

    fun togglePasswordSelection(id: String) {
        val selected = _state.value.selectedPasswordIds
        _state.value = _state.value.copy(
            selectedPasswordIds = if (id in selected) selected - id else selected + id,
        )
    }

    fun clearSelections() {
        _state.value = _state.value.copy(selectedAccountIds = emptySet(), selectedPasswordIds = emptySet())
    }

    fun setSelectedAccountsFavorite(value: Boolean) = mutate("收藏状态已更新") {
        val ids = JSONArray(_state.value.selectedAccountIds.toList()).toString()
        gateway.setAccountFavorite(ids, value).also { clearSelections() }
    }

    fun setSelectedAccountsPinned(value: Boolean) = mutate("置顶状态已更新") {
        val ids = JSONArray(_state.value.selectedAccountIds.toList()).toString()
        gateway.setAccountPinned(ids, value).also { clearSelections() }
    }

    fun deleteSelectedAccounts() = mutate("所选账号已删除") {
        val ids = JSONArray(_state.value.selectedAccountIds.toList()).toString()
        gateway.deleteAccounts(ids).also { clearSelections() }
    }

    fun assignSelectedAccountGroups(groups: List<String>) = mutate("账号分组已更新") {
        val ids = JSONArray(_state.value.selectedAccountIds.toList()).toString()
        gateway.assignAccountGroups(ids, JSONArray(groups).toString()).also { clearSelections() }
    }

    fun setSelectedPasswordsFavorite(value: Boolean) = mutate("收藏状态已更新") {
        val ids = JSONArray(_state.value.selectedPasswordIds.toList()).toString()
        gateway.setPasswordFavorite(ids, value).also { clearSelections() }
    }

    fun setSelectedPasswordsPinned(value: Boolean) = mutate("置顶状态已更新") {
        val ids = JSONArray(_state.value.selectedPasswordIds.toList()).toString()
        gateway.setPasswordPinned(ids, value).also { clearSelections() }
    }

    fun deleteSelectedPasswords() = mutate("所选密码已删除") {
        val ids = JSONArray(_state.value.selectedPasswordIds.toList()).toString()
        gateway.deletePasswords(ids).also { clearSelections() }
    }

    fun assignSelectedPasswordGroups(groups: List<String>) = mutate("密码分组已更新") {
        val ids = JSONArray(_state.value.selectedPasswordIds.toList()).toString()
        gateway.assignPasswordGroups(ids, JSONArray(groups).toString()).also { clearSelections() }
    }
    fun createPasswordGroup(name: String) = mutate("密码分组已创建") { gateway.createPasswordGroup(name) }
    fun renamePasswordGroup(id: String, name: String) = mutate("密码分组已重命名") { gateway.renamePasswordGroup(id, name) }
    fun deletePasswordGroup(id: String) = mutate("密码分组已删除") { gateway.deletePasswordGroup(id) }
    fun assignPasswordGroups(id: String, groups: List<String>) = mutate("密码分组已更新") {
        gateway.assignPasswordGroups(JSONArray().put(id).toString(), JSONArray(groups).toString())
    }

    fun getServer(id: String, callback: (JSONObject) -> Unit) = viewModelScope.launch {
        try {
            callback(JSONObject(invokeGateway { gateway.getServer(id) }))
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "无法读取服务器档案"))
        }
    }

    fun createServer(data: JSONObject) = mutate("服务器已添加") { gateway.createServer(data.toString()) }

    fun updateServer(data: JSONObject) = viewModelScope.launch {
        runBusy {
            val profileId = data.optString("id")
            invokeGateway { gateway.updateServer(data.toString()) }
            if (profileId.isNotBlank()) sshSessions.closeProfile(profileId)
            refreshNow()
            _events.emit(AppEvent.Message("服务器已更新，相关终端已断开"))
        }
    }

    fun deleteServer(profileId: String) = viewModelScope.launch {
        runBusy {
            invokeGateway { gateway.deleteServer(profileId) }
            sshSessions.closeProfile(profileId)
            refreshNow()
            _events.emit(AppEvent.Message("服务器已删除"))
        }
    }

    fun connectServer(profileId: String) = viewModelScope.launch {
        try {
            val profile = JSONObject(invokeGateway { gateway.getServerConnection(profileId) })
            sshSessions.connect(AndroidServerConnection.fromJson(profile))
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "SSH 连接失败"))
        }
    }

    fun disconnectTerminal(sessionId: String) {
        sshSessions.dismiss(sessionId)
    }

    fun sendTerminalInput(sessionId: String, input: String) {
        // Escape, Tab and other terminal control characters are meaningful even though
        // String.isBlank() considers some of them to be whitespace.
        if (input.isEmpty()) return
        try {
            sshSessions.write(sessionId, input)
        } catch (error: Exception) {
            _events.tryEmit(AppEvent.Error(error.message ?: "终端输入失败"))
        }
    }

    fun resizeTerminal(sessionId: String, columns: Int, rows: Int) {
        sshSessions.resize(sessionId, columns, rows)
    }

    fun approveServerHostKey(sessionId: String) = viewModelScope.launch {
        val session = _state.value.serverTerminalSessions.firstOrNull { it.id == sessionId }
        val prompt = session?.hostKeyPrompt ?: run {
            _events.emit(AppEvent.Error("主机指纹确认已失效"))
            return@launch
        }
        try {
            invokeGateway {
                gateway.trustServerHostKey(
                    JSONObject()
                        .put("profile_id", session.profileId)
                        .put("algorithm", prompt.algorithm)
                        .put("key_data", prompt.keyData)
                        .toString(),
                )
            }
            sshSessions.approveHostKey(sessionId)
            refreshNow()
        } catch (error: Exception) {
            sshSessions.rejectHostKey(sessionId)
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "无法保存主机指纹"))
        }
    }

    fun rejectServerHostKey(sessionId: String) {
        sshSessions.rejectHostKey(sessionId)
    }

    fun resetServerHostKey(profileId: String) = viewModelScope.launch {
        runBusy {
            invokeGateway { gateway.resetServerHostKey(profileId) }
            sshSessions.closeProfile(profileId)
            refreshNow()
            _events.emit(AppEvent.Message("已重置主机信任记录"))
        }
    }

    fun getAccount(id: String, callback: (JSONObject) -> Unit) = viewModelScope.launch {
        try {
            callback(JSONObject(invokeGateway { gateway.getAccount(id) }))
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "无法读取验证码账号"))
        }
    }

    fun exportAccountUri(id: String, callback: (String) -> Unit) = viewModelScope.launch {
        try {
            callback(invokeGateway { gateway.exportAccountUri(id) })
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "无法导出 URI"))
        }
    }

    fun getPassword(id: String, callback: (JSONObject) -> Unit) = viewModelScope.launch {
        try {
            val result = JSONObject(invokeGateway { gateway.getPassword(id) })
            callback(result)
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "无法读取密码"))
        }
    }

    fun generatePassword(options: JSONObject, callback: (String) -> Unit) = viewModelScope.launch {
        try { callback(invokeGateway { gateway.generatePassword(options.toString()) }) }
        catch (error: Exception) { _events.emit(AppEvent.Error(error.message ?: "无法生成密码")) }
    }

    fun processQrPayload(uri: String, callback: (JSONObject?) -> Unit) = viewModelScope.launch {
        try {
            val result = JSONObject(invokeGateway { gateway.processQrPayload(uri) })
            if (result.optString("kind") == "single") {
                callback(result.getJSONObject("entry"))
            } else {
                refresh()
                val batch = if (result.optInt("batch_size", 1) > 1) {
                    "，第 ${result.optInt("batch_index") + 1}/${result.optInt("batch_size")} 张"
                } else ""
                _events.emit(
                    AppEvent.Message(
                        "Google 导入完成：新增 ${result.optInt("accounts_added")} 个账号，" +
                            "跳过 ${result.optInt("duplicates_skipped")} 个重复账号$batch",
                    ),
                )
                callback(null)
            }
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "二维码内容无效"))
        }
    }

    fun exportBackup(encrypted: Boolean, callback: (String) -> Unit) = viewModelScope.launch {
        try { callback(invokeGateway { gateway.exportBackup(encrypted) }) }
        catch (error: Exception) { _events.emit(AppEvent.Error(error.cause?.message ?: "导出失败")) }
    }

    fun exportGoogleAuthenticator(callback: (JSONObject) -> Unit) = viewModelScope.launch {
        try {
            callback(JSONObject(invokeGateway { gateway.exportGoogleAuthenticator() }))
        } catch (error: Exception) {
            _events.emit(
                AppEvent.Error(error.cause?.message ?: error.message ?: "无法生成 Google 导入二维码"),
            )
        }
    }

    fun importBackup(content: String, password: String, callback: (Boolean) -> Unit) = viewModelScope.launch {
        try {
            val result = JSONObject(invokeGateway { gateway.importBackup(content, password) })
            if (result.optBoolean("password_required")) callback(true)
            else {
                refresh()
                _events.emit(AppEvent.Message("导入完成"))
                callback(false)
            }
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "导入失败"))
        }
    }

    fun autoLockMinutes(): Int = preferences.getInt("autolock_minutes", 5)
    fun setAutoLockMinutes(value: Int) { preferences.edit().putInt("autolock_minutes", value).apply() }

    fun setAccountSort(value: AccountSortPreference) {
        preferences.edit()
            .putString("account_sort_field", value.sortField.value)
            .putString("account_sort_direction", value.direction.value)
            .apply()
        _state.value = _state.value.copy(accountSort = value)
        refresh()
    }

    fun setPasswordSort(value: PasswordSortPreference) {
        preferences.edit()
            .putString("password_sort_field", value.sortField.value)
            .putString("password_sort_direction", value.direction.value)
            .apply()
        _state.value = _state.value.copy(passwordSort = value)
        refresh()
    }

    fun onBackground() {
        backgroundAt = System.currentTimeMillis()
        ticker?.cancel()
        sshSessions.clearAll()
        _state.value = _state.value.copy(privacyShield = true)
    }

    fun onForeground() {
        val minutes = autoLockMinutes()
        val elapsed = System.currentTimeMillis() - backgroundAt
        if (!_state.value.locked && backgroundAt > 0 && minutes > 0 && elapsed >= minutes * 60_000L) {
            lock("保险库已自动锁定")
        } else {
            _state.value = _state.value.copy(privacyShield = false)
            if (!_state.value.locked) startTicker()
        }
    }

    override fun onCleared() {
        sshSessions.clearAll()
        super.onCleared()
    }
}
