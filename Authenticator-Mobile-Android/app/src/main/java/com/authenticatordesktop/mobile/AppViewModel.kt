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
import kotlinx.coroutines.launch
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
    val selectedAccountIds: Set<String> = emptySet(),
    val selectedPasswordIds: Set<String> = emptySet(),
    val accountSort: AccountSortPreference = AccountSortPreference(),
    val passwordSort: PasswordSortPreference = PasswordSortPreference(),
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
    private var ticker: Job? = null
    private var backgroundAt = 0L

    init { startup() }

    private fun startup() = viewModelScope.launch {
        runBusy {
            val result = JSONObject(gateway.startup())
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
            withContext(Dispatchers.IO) { block() }
        } catch (error: Exception) {
            _state.value = _state.value.copy(loading = false)
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "操作失败"))
        }
    }

    fun initialize(password: String) = mutate("保险库已创建") { gateway.initialize(password) }
    fun unlock(password: String) = mutate("保险库已解锁") { gateway.unlock(password) }

    fun lock(message: String = "保险库已锁定") = viewModelScope.launch {
        runBusy {
            gateway.lock()
            ticker?.cancel()
            _state.value = _state.value.copy(
                locked = true,
                snapshot = VaultSnapshot(),
                privacyShield = false,
                selectedAccountIds = emptySet(),
                selectedPasswordIds = emptySet(),
            )
            _events.emit(AppEvent.Message(message))
        }
    }

    fun changeMasterPassword(current: String, next: String) =
        mutate("主密码已修改") { gateway.changeMasterPassword(current, next) }

    fun setAccountQuery(value: String) { _state.value = _state.value.copy(accountQuery = value, selectedAccountIds = emptySet()); refresh() }
    fun setPasswordQuery(value: String) { _state.value = _state.value.copy(passwordQuery = value, selectedPasswordIds = emptySet()); refresh() }
    fun setAccountGroup(value: String) { _state.value = _state.value.copy(accountGroup = value, selectedAccountIds = emptySet()); refresh() }
    fun setPasswordGroup(value: String) { _state.value = _state.value.copy(passwordGroup = value, selectedPasswordIds = emptySet()); refresh() }
    fun setAccountFavoriteOnly(value: Boolean) { _state.value = _state.value.copy(accountFavoriteOnly = value, selectedAccountIds = emptySet()); refresh() }
    fun setPasswordFavoriteOnly(value: Boolean) { _state.value = _state.value.copy(passwordFavoriteOnly = value, selectedPasswordIds = emptySet()); refresh() }
    fun setAccountShowPinned(value: Boolean) {
        preferences.edit().putBoolean("account_show_pinned", value).apply()
        _state.value = _state.value.copy(accountShowPinned = value, selectedAccountIds = emptySet())
        refresh()
    }
    fun setPasswordShowPinned(value: Boolean) {
        preferences.edit().putBoolean("password_show_pinned", value).apply()
        _state.value = _state.value.copy(passwordShowPinned = value, selectedPasswordIds = emptySet())
        refresh()
    }

    fun refresh() = viewModelScope.launch { runBusy { refreshNow() } }

    private fun refreshNow() {
        if (_state.value.locked) return
        val state = _state.value
        val snapshot = parseSnapshot(
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
            ),
        )
        _state.value = state.copy(loading = false, locked = false, setupRequired = false, snapshot = snapshot)
        if (ticker == null || ticker?.isActive != true) startTicker()
    }

    private fun startTicker() {
        ticker?.cancel()
        ticker = viewModelScope.launch {
            while (true) {
                delay(1_000)
                runBusy { refreshNow() }
            }
        }
    }

    private fun mutate(message: String, action: () -> String) = viewModelScope.launch {
        runBusy {
            action()
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

    fun getPassword(id: String, callback: (JSONObject) -> Unit) = viewModelScope.launch {
        try {
            val result = withContext(Dispatchers.IO) { JSONObject(gateway.getPassword(id)) }
            callback(result)
        } catch (error: Exception) {
            _events.emit(AppEvent.Error(error.cause?.message ?: error.message ?: "无法读取密码"))
        }
    }

    fun generatePassword(options: JSONObject, callback: (String) -> Unit) = viewModelScope.launch {
        try { callback(withContext(Dispatchers.IO) { gateway.generatePassword(options.toString()) }) }
        catch (error: Exception) { _events.emit(AppEvent.Error(error.message ?: "无法生成密码")) }
    }

    fun processQrPayload(uri: String, callback: (JSONObject?) -> Unit) = viewModelScope.launch {
        try {
            val result = withContext(Dispatchers.IO) { JSONObject(gateway.processQrPayload(uri)) }
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
        try { callback(withContext(Dispatchers.IO) { gateway.exportBackup(encrypted) }) }
        catch (error: Exception) { _events.emit(AppEvent.Error(error.cause?.message ?: "导出失败")) }
    }

    fun exportGoogleAuthenticator(callback: (JSONObject) -> Unit) = viewModelScope.launch {
        try {
            callback(withContext(Dispatchers.IO) { JSONObject(gateway.exportGoogleAuthenticator()) })
        } catch (error: Exception) {
            _events.emit(
                AppEvent.Error(error.cause?.message ?: error.message ?: "无法生成 Google 导入二维码"),
            )
        }
    }

    fun importBackup(content: String, password: String, callback: (Boolean) -> Unit) = viewModelScope.launch {
        try {
            val result = withContext(Dispatchers.IO) { JSONObject(gateway.importBackup(content, password)) }
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
        _state.value = _state.value.copy(privacyShield = true)
    }

    fun onForeground() {
        val minutes = autoLockMinutes()
        val elapsed = System.currentTimeMillis() - backgroundAt
        if (!_state.value.locked && backgroundAt > 0 && minutes > 0 && elapsed >= minutes * 60_000L) {
            lock("保险库已自动锁定")
        } else {
            _state.value = _state.value.copy(privacyShield = false)
        }
    }
}
