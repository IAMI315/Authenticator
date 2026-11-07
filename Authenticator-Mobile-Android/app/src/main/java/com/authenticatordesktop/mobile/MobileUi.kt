@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.ExperimentalFoundationApi::class,
)

package com.authenticatordesktop.mobile

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Sort
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Computer
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material.icons.rounded.FileUpload
import androidx.compose.material.icons.rounded.Folder
import androidx.compose.material.icons.rounded.Key
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Password
import androidx.compose.material.icons.rounded.PushPin
import androidx.compose.material.icons.rounded.QrCodeScanner
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import org.json.JSONObject

private enum class MobileModule(val label: String, val icon: ImageVector) {
    OTP("验证码", Icons.Rounded.Key),
    PASSWORDS("密码本", Icons.Rounded.Password),
    SERVERS("服务器", Icons.Rounded.Computer),
    SETTINGS("设置", Icons.Rounded.Settings),
}

@Composable
fun AuthenticatorMobileApp(viewModel: AppViewModel) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var module by remember { mutableStateOf(MobileModule.OTP) }
    var accountEditor by remember { mutableStateOf<JSONObject?>(null) }
    var showNewAccount by remember { mutableStateOf(false) }
    var passwordEditor by remember { mutableStateOf<JSONObject?>(null) }
    var showNewPassword by remember { mutableStateOf(false) }
    var serverEditor by remember { mutableStateOf<JSONObject?>(null) }
    var showNewServer by remember { mutableStateOf(false) }
    var deleteServer by remember { mutableStateOf<ServerRow?>(null) }
    var privateKeyReceiver by remember { mutableStateOf<((String) -> Unit)?>(null) }
    var assignmentAccount by remember { mutableStateOf<AccountRow?>(null) }
    var assignmentPassword by remember { mutableStateOf<PasswordRow?>(null) }
    var changeMasterPassword by remember { mutableStateOf(false) }
    var showScanner by remember { mutableStateOf(false) }
    var showUriImport by remember { mutableStateOf(false) }
    var pendingImport by remember { mutableStateOf<String?>(null) }
    var pendingExport by remember { mutableStateOf<String?>(null) }
    var accountUri by remember { mutableStateOf<String?>(null) }
    var revealedPassword by remember { mutableStateOf<Pair<String, String>?>(null) }
    var deleteAccountId by remember { mutableStateOf<String?>(null) }
    var deletePasswordId by remember { mutableStateOf<String?>(null) }
    var assignSelectedAccounts by remember { mutableStateOf(false) }
    var assignSelectedPasswords by remember { mutableStateOf(false) }
    var deleteSelectedAccounts by remember { mutableStateOf(false) }
    var deleteSelectedPasswords by remember { mutableStateOf(false) }
    var confirmPlainExport by remember { mutableStateOf(false) }
    var confirmGoogleExport by remember { mutableStateOf(false) }
    var googleExport by remember { mutableStateOf<JSONObject?>(null) }

    fun notify(message: String) { scope.launch { snackbar.showSnackbar(message) } }
    fun copy(label: String, value: String) {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText(label, value))
        notify("已复制$label")
    }

    val openDocument = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        val content = context.contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
        if (content == null) notify("无法读取所选文件")
        else viewModel.importBackup(content, "") { required -> if (required) pendingImport = content }
    }
    val createDocument = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        val content = pendingExport
        pendingExport = null
        if (uri != null && content != null) {
            context.contentResolver.openOutputStream(uri, "w")?.bufferedWriter(Charsets.UTF_8)?.use { it.write(content) }
            notify("备份已导出")
        }
    }
    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) showScanner = true else notify("需要相机权限才能扫码")
    }
    val openPrivateKey = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val receiver = privateKeyReceiver
        privateKeyReceiver = null
        uri ?: return@rememberLauncherForActivityResult
        val content = context.contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
        if (content.isNullOrBlank()) notify("无法读取私钥文件")
        else if (content.toByteArray(Charsets.UTF_8).size > 65_536) notify("私钥文件不能超过 64 KB")
        else receiver?.invoke(content)
    }

    LaunchedEffect(viewModel) {
        viewModel.events.collectLatest { event ->
            when (event) {
                is AppEvent.Error -> snackbar.showSnackbar(event.value)
                is AppEvent.Message -> snackbar.showSnackbar(event.value)
            }
        }
    }

    BackHandler(
        enabled = state.selectedAccountIds.isNotEmpty() || state.selectedPasswordIds.isNotEmpty(),
        onBack = viewModel::clearSelections,
    )

    when {
        state.loading -> LoadingScreen()
        state.setupRequired -> SecurityScreen("创建主密码", "首次使用需要创建本地保险库", true) { viewModel.initialize(it) }
        state.locked -> SecurityScreen("保险库已锁定", "输入主密码以查看验证码和密码", false) { viewModel.unlock(it) }
        else -> {
            Scaffold(
                containerColor = WindowBackground,
                snackbarHost = { SnackbarHost(snackbar) },
                topBar = {
                    TopAppBar(
                        colors = TopAppBarDefaults.topAppBarColors(containerColor = GlassSurface),
                        title = {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                                    AppIcon(Modifier.size(41.dp))
                                }
                                Spacer(Modifier.width(10.dp))
                                Column {
                                    Text("验证器", fontWeight = FontWeight.SemiBold)
                                    Text("本地加密保险库", style = MaterialTheme.typography.labelSmall, color = FreshGreen)
                                }
                            }
                        },
                        actions = {
                            IconButton(onClick = { viewModel.lock() }) { Icon(Icons.Rounded.Lock, "锁定保险库") }
                        },
                    )
                },
                bottomBar = {
                    NavigationBar(containerColor = GlassSurface, modifier = Modifier.navigationBarsPadding()) {
                        MobileModule.entries.forEach { item ->
                            NavigationBarItem(
                                selected = module == item,
                                onClick = { viewModel.clearSelections(); module = item },
                                icon = { Icon(item.icon, item.label) },
                                label = { Text(item.label) },
                            )
                        }
                    }
                },
                floatingActionButton = {
                    if (state.selectedAccountIds.isNotEmpty() || state.selectedPasswordIds.isNotEmpty()) Unit else when (module) {
                        MobileModule.OTP -> Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            FloatingActionButton(onClick = { showNewAccount = true }, containerColor = MaterialTheme.colorScheme.surface) {
                                Icon(Icons.Rounded.Add, "手动新增")
                            }
                            ExtendedFloatingActionButton(
                                onClick = { cameraPermission.launch(Manifest.permission.CAMERA) },
                                icon = { Icon(Icons.Rounded.QrCodeScanner, null) },
                                text = { Text("扫码新增") },
                            )
                        }
                        MobileModule.PASSWORDS -> ExtendedFloatingActionButton(
                            onClick = { showNewPassword = true },
                            icon = { Icon(Icons.Rounded.Add, null) },
                            text = { Text("新增密码") },
                        )
                        MobileModule.SERVERS -> Unit
                        MobileModule.SETTINGS -> Unit
                    }
                },
            ) { padding ->
                Box(Modifier.fillMaxSize().padding(padding)) {
                    when (module) {
                        MobileModule.OTP -> OtpScreen(
                            state,
                            viewModel,
                            copy = ::copy,
                            edit = { row -> viewModel.getAccount(row.id) { accountEditor = it } },
                            showUri = { row -> viewModel.exportAccountUri(row.id) { accountUri = it } },
                            assign = { assignmentAccount = it },
                            requestDelete = { deleteAccountId = it.id },
                            assignSelected = { assignSelectedAccounts = true },
                            deleteSelected = { deleteSelectedAccounts = true },
                        )
                        MobileModule.PASSWORDS -> PasswordScreen(
                            state,
                            viewModel,
                            copy = ::copy,
                            edit = { row -> viewModel.getPassword(row.id) { passwordEditor = it } },
                            assign = { assignmentPassword = it },
                            reveal = { row -> viewModel.getPassword(row.id) { revealedPassword = row.title to it.optString("password") } },
                            requestDelete = { deletePasswordId = it.id },
                            assignSelected = { assignSelectedPasswords = true },
                            deleteSelected = { deleteSelectedPasswords = true },
                        )
                        MobileModule.SERVERS -> ServerScreen(
                            state = state,
                            viewModel = viewModel,
                            onCreate = { showNewServer = true },
                            onEdit = { row -> viewModel.getServer(row.id) { serverEditor = it } },
                            onDelete = { deleteServer = it },
                        )
                        MobileModule.SETTINGS -> SettingsScreen(
                            autoLock = viewModel.autoLockMinutes(),
                            onAutoLock = viewModel::setAutoLockMinutes,
                            accountSort = state.accountSort,
                            passwordSort = state.passwordSort,
                            onAccountSort = viewModel::setAccountSort,
                            onPasswordSort = viewModel::setPasswordSort,
                            onChangePassword = { changeMasterPassword = true },
                            onImport = { openDocument.launch(arrayOf("application/json", "application/octet-stream", "text/plain")) },
                            onImportUri = { showUriImport = true },
                            onGoogleExport = { confirmGoogleExport = true },
                            onExport = { encrypted ->
                                if (!encrypted) {
                                    confirmPlainExport = true
                                } else {
                                    viewModel.exportBackup(true) { content ->
                                        pendingExport = content
                                        createDocument.launch("authenticator-backup.authbak")
                                    }
                                }
                            },
                            groups = state.snapshot.groups,
                            passwordGroups = state.snapshot.passwordGroups,
                            viewModel = viewModel,
                        )
                    }
                    if (state.privacyShield) PrivacyShield()
                }
            }
        }
    }

    if (showScanner) QrScannerScreen(
        onDecoded = { value ->
            showScanner = false
            viewModel.processQrPayload(value) { parsed ->
                if (parsed != null) {
                    accountEditor = parsed
                    showNewAccount = true
                }
            }
        },
        onClose = { showScanner = false },
    )
    if (showUriImport) UriImportDialog(
        onClose = { showUriImport = false },
        onImport = { uri ->
            showUriImport = false
            viewModel.processQrPayload(uri) { parsed ->
                if (parsed != null) {
                    accountEditor = parsed
                    showNewAccount = true
                }
            }
        },
    )
    if (showNewAccount || accountEditor != null) AccountEditorDialog(
        initial = accountEditor,
        groups = state.snapshot.groups,
        onClose = { showNewAccount = false; accountEditor = null },
        onSave = { data ->
            if (showNewAccount) viewModel.createAccount(data) else viewModel.updateAccount(data)
            showNewAccount = false; accountEditor = null
        },
    )
    if (showNewPassword || passwordEditor != null) PasswordEditorDialog(
        initial = passwordEditor,
        groups = state.snapshot.passwordGroups,
        generatedPassword = viewModel::generatePassword,
        onClose = { showNewPassword = false; passwordEditor = null },
        onSave = { data ->
            val id = passwordEditor?.optString("id").orEmpty()
            if (id.isBlank()) viewModel.createPassword(data) else viewModel.updatePassword(id, data)
            showNewPassword = false; passwordEditor = null
        },
    )
    if (showNewServer || serverEditor != null) ServerEditorDialog(
        initial = serverEditor,
        onPickPrivateKey = { receiver ->
            privateKeyReceiver = receiver
            openPrivateKey.launch(arrayOf("application/octet-stream", "text/plain", "application/x-pem-file", "*/*"))
        },
        onClose = {
            privateKeyReceiver = null
            showNewServer = false
            serverEditor = null
        },
        onSave = { data ->
            if (data.optString("id").isBlank()) viewModel.createServer(data) else viewModel.updateServer(data)
            privateKeyReceiver = null
            showNewServer = false
            serverEditor = null
        },
    )
    assignmentAccount?.let { item ->
        GroupAssignmentDialog("调整账号分组", state.snapshot.groups, item.groupIds, "default", { assignmentAccount = null }) {
            viewModel.assignAccountGroups(item.id, it); assignmentAccount = null
        }
    }
    assignmentPassword?.let { item ->
        GroupAssignmentDialog("调整密码分组", state.snapshot.passwordGroups, item.groupIds, "password-default", { assignmentPassword = null }) {
            viewModel.assignPasswordGroups(item.id, it); assignmentPassword = null
        }
    }
    if (assignSelectedAccounts) {
        val selected = state.snapshot.accounts.filter { it.id in state.selectedAccountIds }
        val common = selected.map { it.groupIds.toSet() }.reduceOrNull(Set<String>::intersect).orEmpty().toList()
        GroupAssignmentDialog("批量调整账号分组", state.snapshot.groups, common, "default", { assignSelectedAccounts = false }) {
            viewModel.assignSelectedAccountGroups(it); assignSelectedAccounts = false
        }
    }
    if (assignSelectedPasswords) {
        val selected = state.snapshot.passwords.filter { it.id in state.selectedPasswordIds }
        val common = selected.map { it.groupIds.toSet() }.reduceOrNull(Set<String>::intersect).orEmpty().toList()
        GroupAssignmentDialog("批量调整密码分组", state.snapshot.passwordGroups, common, "password-default", { assignSelectedPasswords = false }) {
            viewModel.assignSelectedPasswordGroups(it); assignSelectedPasswords = false
        }
    }
    if (changeMasterPassword) MasterPasswordDialog("修改主密码", true, { changeMasterPassword = false }) { current, next ->
        viewModel.changeMasterPassword(current, next); changeMasterPassword = false
    }
    pendingImport?.let { content ->
        PasswordInputDialog("输入备份主密码", { pendingImport = null }) { password ->
            viewModel.importBackup(content, password) { required -> if (!required) pendingImport = null }
        }
    }
    revealedPassword?.let { (title, password) ->
        SecretDialog(title, password, { revealedPassword = null }) { copy("密码", password) }
    }
    accountUri?.let { uri ->
        SecretDialog("otpauth URI", uri, { accountUri = null }) { copy("URI", uri) }
    }
    deleteAccountId?.let { id ->
        ConfirmDialog("删除验证码账号？", "此操作会从本机保险库永久删除该账号。", { deleteAccountId = null }) {
            viewModel.deleteAccount(id); deleteAccountId = null
        }
    }
    deletePasswordId?.let { id ->
        ConfirmDialog("删除密码记录？", "此操作会从本机保险库永久删除该密码记录。", { deletePasswordId = null }) {
            viewModel.deletePassword(id); deletePasswordId = null
        }
    }
    deleteServer?.let { profile ->
        ConfirmDialog(
            "删除服务器？",
            "将删除“${profile.name}”及其中保存的认证资料，并断开相关 SSH 终端。",
            { deleteServer = null },
        ) {
            viewModel.deleteServer(profile.id)
            deleteServer = null
        }
    }
    if (deleteSelectedAccounts) {
        ConfirmDialog("删除所选账号？", "将永久删除所选 ${state.selectedAccountIds.size} 个账号。", { deleteSelectedAccounts = false }) {
            viewModel.deleteSelectedAccounts(); deleteSelectedAccounts = false
        }
    }
    if (deleteSelectedPasswords) {
        ConfirmDialog("删除所选密码？", "将永久删除所选 ${state.selectedPasswordIds.size} 条密码记录。", { deleteSelectedPasswords = false }) {
            viewModel.deleteSelectedPasswords(); deleteSelectedPasswords = false
        }
    }
    if (confirmPlainExport) {
        ConfirmDialog("导出明文 JSON？", "文件会直接包含验证码密钥和密码，请只保存到可信位置。", { confirmPlainExport = false }, confirmLabel = "继续导出") {
            confirmPlainExport = false
            viewModel.exportBackup(false) { content ->
                pendingExport = content
                createDocument.launch("authenticator-backup.json")
            }
        }
    }
    if (confirmGoogleExport) {
        ConfirmDialog(
            "生成 Google 导入二维码？",
            "二维码会直接包含验证码账号密钥，请确保周围没有他人，并只使用可信设备扫描。",
            { confirmGoogleExport = false },
            confirmLabel = "生成二维码",
        ) {
            confirmGoogleExport = false
            viewModel.exportGoogleAuthenticator { googleExport = it }
        }
    }
    googleExport?.let { export ->
        GoogleAuthenticatorExportDialog(export, onClose = { googleExport = null })
    }
}

@Composable
private fun LoadingScreen() = Box(Modifier.fillMaxSize().background(WindowBackground), contentAlignment = Alignment.Center) {
    CircularProgressIndicator()
}

@Composable
private fun PrivacyShield() = Box(
    Modifier.fillMaxSize().background(WindowBackground).semantics { contentDescription = "敏感内容已隐藏" },
    contentAlignment = Alignment.Center,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        AppIcon(Modifier.size(52.dp))
        Text("验证器", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        Text("敏感内容已隐藏", color = TextMuted)
    }
}

@Composable
private fun SecurityScreen(title: String, subtitle: String, confirm: Boolean, submit: (String) -> Unit) {
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    Box(Modifier.fillMaxSize().background(WindowBackground).padding(24.dp), contentAlignment = Alignment.Center) {
        Card(
            modifier = Modifier.fillMaxWidth().widthIn(max = 440.dp),
            shape = RoundedCornerShape(8.dp),
            colors = CardDefaults.cardColors(containerColor = GlassSurface),
            border = androidx.compose.foundation.BorderStroke(1.dp, GlassBorder),
        ) {
            Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Surface(shape = RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                    AppIcon(Modifier.size(68.dp))
                }
                Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = TextMuted)
                OutlinedTextField(password, { password = it }, label = { Text("主密码") }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
                if (confirm) OutlinedTextField(confirmation, { confirmation = it }, label = { Text("确认主密码") }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
                Button(onClick = { submit(password) }, enabled = password.length >= 8 && (!confirm || password == confirmation), modifier = Modifier.fillMaxWidth().height(50.dp)) {
                    Text(if (confirm) "创建保险库" else "解锁")
                }
                Text("数据只保存在本机并经过加密", style = MaterialTheme.typography.bodySmall, color = TextMuted)
            }
        }
    }
}

@Composable
private fun SearchField(value: String, placeholder: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value, onChange, modifier = Modifier.fillMaxWidth(), singleLine = true,
        leadingIcon = { Icon(Icons.Rounded.Search, null) }, placeholder = { Text(placeholder) },
        shape = RoundedCornerShape(8.dp),
    )
}

@Composable
private fun FilterRow(
    groups: List<GroupRow>,
    selected: String,
    favoriteOnly: Boolean,
    showPinned: Boolean,
    onGroup: (String) -> Unit,
    onFavorite: (Boolean) -> Unit,
    onShowPinned: (Boolean) -> Unit,
    providers: List<ProviderFilterRow> = emptyList(),
    selectedProviderKey: String = "",
    otherProvidersOnly: Boolean = false,
    onProvider: (String) -> Unit = {},
    onOtherProviders: () -> Unit = {},
    otherProviderCount: Int = 0,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 2.dp)) {
            item { FilterChip(selected = selected.isBlank(), onClick = { onGroup("") }, label = { Text("全部") }) }
            item { FilterChip(selected = favoriteOnly, onClick = { onFavorite(!favoriteOnly) }, leadingIcon = { Icon(Icons.Rounded.Star, null, Modifier.size(17.dp)) }, label = { Text("收藏") }) }
            item { FilterChip(selected = showPinned, onClick = { onShowPinned(!showPinned) }, leadingIcon = { Icon(Icons.Rounded.PushPin, null, Modifier.size(17.dp)) }, label = { Text("置顶可见") }) }
            items(groups.filterNot { it.id == "default" || it.id == "password-default" }) { group ->
                FilterChip(selected = selected == group.id, onClick = { onGroup(if (selected == group.id) "" else group.id) }, label = { Text(group.name) })
            }
        }
        if (providers.isNotEmpty() || otherProviderCount > 0) {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 2.dp)) {
                item { Text("服务商", style = MaterialTheme.typography.labelMedium, color = TextMuted, modifier = Modifier.padding(top = 8.dp, end = 2.dp)) }
                items(providers, key = { it.key }) { provider ->
                    FilterChip(
                        selected = selectedProviderKey == provider.key,
                        onClick = { onProvider(provider.key) },
                        label = { Text("${provider.label} ${provider.count}") },
                    )
                }
                if (otherProviderCount > 0) {
                    item {
                        FilterChip(
                            selected = otherProvidersOnly,
                            onClick = onOtherProviders,
                            label = { Text("其他服务商 $otherProviderCount") },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun OtpScreen(
    state: AppState,
    viewModel: AppViewModel,
    copy: (String, String) -> Unit,
    edit: (AccountRow) -> Unit,
    showUri: (AccountRow) -> Unit,
    assign: (AccountRow) -> Unit,
    requestDelete: (AccountRow) -> Unit,
    assignSelected: () -> Unit,
    deleteSelected: () -> Unit,
) {
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Spacer(Modifier.height(4.dp))
        SearchField(state.accountQuery, "搜索服务商或账号", viewModel::setAccountQuery)
        FilterRow(
            state.snapshot.groups,
            state.accountGroup,
            state.accountFavoriteOnly,
            state.accountShowPinned,
            viewModel::setAccountGroup,
            viewModel::setAccountFavoriteOnly,
            viewModel::setAccountShowPinned,
            state.snapshot.accountProviders,
            state.accountProviderKey,
            state.accountOtherProvidersOnly,
            viewModel::setAccountProvider,
            viewModel::setOtherAccountProvidersOnly,
            state.snapshot.otherProviderCount,
        )
        if (state.selectedAccountIds.isNotEmpty()) {
            SelectionActionBar(
                state.selectedAccountIds.size,
                viewModel::clearSelections,
                { viewModel.setSelectedAccountsFavorite(true) },
                { viewModel.setSelectedAccountsFavorite(false) },
                { viewModel.setSelectedAccountsPinned(true) },
                { viewModel.setSelectedAccountsPinned(false) },
                assignSelected,
                deleteSelected,
            )
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("${state.snapshot.accounts.size} 个账号", style = MaterialTheme.typography.labelLarge, color = TextMuted)
            Spacer(Modifier.weight(1f))
            Text("分组可在设置中管理", style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
        if (state.snapshot.accounts.isEmpty()) EmptyState("暂无验证码", "点击右下角扫码或手动新增")
        else LazyColumn(contentPadding = PaddingValues(bottom = 104.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(state.snapshot.accounts, key = { it.id }) { item ->
                OtpCard(
                    item,
                    copy,
                    { edit(item) },
                    { showUri(item) },
                    { assign(item) },
                    { viewModel.setAccountFavorite(item.id, !item.favorite) },
                    { viewModel.toggleAccountPinned(item.id) },
                    { requestDelete(item) },
                    { viewModel.incrementHotp(item.id) },
                    item.id in state.selectedAccountIds,
                    state.selectedAccountIds.isNotEmpty(),
                    { viewModel.toggleAccountSelection(item.id) },
                )
            }
        }
    }
}

@Composable
private fun OtpCard(
    item: AccountRow,
    copy: (String, String) -> Unit,
    edit: () -> Unit,
    showUri: () -> Unit,
    assign: () -> Unit,
    favorite: () -> Unit,
    pin: () -> Unit,
    delete: () -> Unit,
    next: () -> Unit,
    selected: Boolean,
    selectionMode: Boolean,
    toggleSelection: () -> Unit,
) {
    var menu by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth().combinedClickable(
            onClick = { if (selectionMode) toggleSelection() },
            onLongClick = toggleSelection,
        ), shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = GlassSurface),
        border = androidx.compose.foundation.BorderStroke(1.dp, GlassBorder),
    ) {
        Row(Modifier.padding(start = 14.dp, top = 13.dp, bottom = 13.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            if (selectionMode) Checkbox(selected, { toggleSelection() })
            Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primaryContainer) {
                Text((item.issuer.ifBlank { "?" }).take(1).uppercase(), modifier = Modifier.padding(11.dp), color = AccentBlue, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(item.issuer.ifBlank { "未命名服务" }, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text(
                    item.account.ifBlank { "未填写账号" },
                    modifier = Modifier.clickable(enabled = item.account.isNotBlank()) { copy("账号", item.account) },
                    color = TextMuted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    item.code.chunked(3).joinToString(" "),
                    modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable { copy("验证码", item.code) }.padding(vertical = 3.dp),
                    color = AccentBlue, fontSize = 25.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp,
                )
            }
            if (!selectionMode) Column(horizontalAlignment = Alignment.CenterHorizontally) {
                IconButton(onClick = favorite, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Rounded.Star, if (item.favorite) "取消收藏" else "收藏", tint = if (item.favorite) WarmOrange else TextMuted, modifier = Modifier.size(18.dp))
                }
                IconButton(onClick = pin, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Rounded.PushPin, if (item.pinned) "取消置顶" else "置顶", tint = if (item.pinned) AccentBlue else TextMuted, modifier = Modifier.size(18.dp))
                }
            }
            if (item.remaining != null) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(42.dp)) {
                    CircularProgressIndicator(
                        progress = { item.remaining.toFloat() / item.period.coerceAtLeast(1) },
                        modifier = Modifier.size(38.dp), strokeWidth = 3.dp, strokeCap = StrokeCap.Round,
                        color = if (item.remaining <= 10) WarmOrange else AccentBlue, trackColor = GlassBorder,
                    )
                    Text(item.remaining.toString(), style = MaterialTheme.typography.labelSmall)
                }
            }
            if (!selectionMode) Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Rounded.MoreVert, "账号操作") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem({ Text("复制账号") }, { menu = false; copy("账号", item.account) }, leadingIcon = { Icon(Icons.Rounded.ContentCopy, null) })
                    DropdownMenuItem({ Text("编辑") }, { menu = false; edit() }, leadingIcon = { Icon(Icons.Rounded.Edit, null) })
                    DropdownMenuItem({ Text("查看 URI") }, { menu = false; showUri() }, leadingIcon = { Icon(Icons.Rounded.ContentCopy, null) })
                    DropdownMenuItem({ Text("分组") }, { menu = false; assign() }, leadingIcon = { Icon(Icons.Rounded.Folder, null) })
                    DropdownMenuItem({ Text(if (item.favorite) "取消收藏" else "收藏") }, { menu = false; favorite() }, leadingIcon = { Icon(Icons.Rounded.Star, null) })
                    DropdownMenuItem({ Text(if (item.pinned) "取消置顶" else "置顶") }, { menu = false; pin() }, leadingIcon = { Icon(Icons.Rounded.PushPin, null) })
                    if (item.otpType == "hotp") DropdownMenuItem({ Text("下一个 HOTP") }, { menu = false; next() })
                    DropdownMenuItem({ Text("删除", color = MaterialTheme.colorScheme.error) }, { menu = false; delete() }, leadingIcon = { Icon(Icons.Rounded.Delete, null, tint = MaterialTheme.colorScheme.error) })
                }
            }
        }
    }
}

@Composable
private fun PasswordScreen(
    state: AppState,
    viewModel: AppViewModel,
    copy: (String, String) -> Unit,
    edit: (PasswordRow) -> Unit,
    assign: (PasswordRow) -> Unit,
    reveal: (PasswordRow) -> Unit,
    requestDelete: (PasswordRow) -> Unit,
    assignSelected: () -> Unit,
    deleteSelected: () -> Unit,
) {
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Spacer(Modifier.height(4.dp))
        SearchField(state.passwordQuery, "搜索名称、用户名或网址", viewModel::setPasswordQuery)
        FilterRow(
            state.snapshot.passwordGroups,
            state.passwordGroup,
            state.passwordFavoriteOnly,
            state.passwordShowPinned,
            viewModel::setPasswordGroup,
            viewModel::setPasswordFavoriteOnly,
            viewModel::setPasswordShowPinned,
        )
        if (state.selectedPasswordIds.isNotEmpty()) {
            SelectionActionBar(
                state.selectedPasswordIds.size,
                viewModel::clearSelections,
                { viewModel.setSelectedPasswordsFavorite(true) },
                { viewModel.setSelectedPasswordsFavorite(false) },
                { viewModel.setSelectedPasswordsPinned(true) },
                { viewModel.setSelectedPasswordsPinned(false) },
                assignSelected,
                deleteSelected,
            )
        }
        Text("${state.snapshot.passwords.size} 条密码记录", style = MaterialTheme.typography.labelLarge, color = TextMuted)
        if (state.snapshot.passwords.isEmpty()) EmptyState("密码本为空", "点击右下角添加第一条密码")
        else LazyColumn(contentPadding = PaddingValues(bottom = 100.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(state.snapshot.passwords, key = { it.id }) { item ->
                PasswordCard(
                    item,
                    copy,
                    { viewModel.getPassword(item.id) { copy("密码", it.optString("password")) } },
                    { reveal(item) },
                    { edit(item) },
                    { assign(item) },
                    { viewModel.setPasswordFavorite(item, !item.favorite) },
                    { viewModel.togglePasswordPinned(item) },
                    { requestDelete(item) },
                    item.id in state.selectedPasswordIds,
                    state.selectedPasswordIds.isNotEmpty(),
                    { viewModel.togglePasswordSelection(item.id) },
                )
            }
        }
    }
}

@Composable
private fun PasswordCard(
    item: PasswordRow,
    copy: (String, String) -> Unit,
    copyPassword: () -> Unit,
    reveal: () -> Unit,
    edit: () -> Unit,
    assign: () -> Unit,
    favorite: () -> Unit,
    pin: () -> Unit,
    delete: () -> Unit,
    selected: Boolean,
    selectionMode: Boolean,
    toggleSelection: () -> Unit,
) {
    var menu by remember { mutableStateOf(false) }
    val context = LocalContext.current
    Card(
        modifier = Modifier.fillMaxWidth().combinedClickable(
            onClick = { if (selectionMode) toggleSelection() },
            onLongClick = toggleSelection,
        ), shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = GlassSurface), border = androidx.compose.foundation.BorderStroke(1.dp, GlassBorder),
    ) {
        Row(Modifier.padding(start = 14.dp, top = 14.dp, bottom = 14.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            if (selectionMode) Checkbox(selected, { toggleSelection() })
            Surface(shape = CircleShape, color = Color(0xFFEDE8FF)) { Icon(Icons.Rounded.Password, null, tint = SoftPurple, modifier = Modifier.padding(11.dp).size(22.dp)) }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(item.title, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text(
                    item.username,
                    modifier = Modifier.clickable { copy("用户名", item.username) },
                    color = TextMuted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text("••••••••••••", modifier = Modifier.clickable { copyPassword() }, color = SoftPurple, letterSpacing = 1.sp)
            }
            if (!selectionMode) Column(horizontalAlignment = Alignment.CenterHorizontally) {
                IconButton(onClick = favorite, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Rounded.Star, if (item.favorite) "取消收藏" else "收藏", tint = if (item.favorite) WarmOrange else TextMuted, modifier = Modifier.size(18.dp))
                }
                IconButton(onClick = pin, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Rounded.PushPin, if (item.pinned) "取消置顶" else "置顶", tint = if (item.pinned) AccentBlue else TextMuted, modifier = Modifier.size(18.dp))
                }
            }
            if (!selectionMode) IconButton(onClick = { copy("用户名", item.username) }) { Icon(Icons.Rounded.ContentCopy, "复制用户名") }
            if (!selectionMode) Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Rounded.MoreVert, "密码操作") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem({ Text("复制密码") }, { menu = false; copyPassword() }, leadingIcon = { Icon(Icons.Rounded.ContentCopy, null) })
                    DropdownMenuItem({ Text("显示密码") }, { menu = false; reveal() })
                    if (isSafeWebUrl(item.url)) DropdownMenuItem({ Text("打开网站") }, {
                        menu = false
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(item.url)))
                    })
                    DropdownMenuItem({ Text("编辑") }, { menu = false; edit() }, leadingIcon = { Icon(Icons.Rounded.Edit, null) })
                    DropdownMenuItem({ Text("分组") }, { menu = false; assign() }, leadingIcon = { Icon(Icons.Rounded.Folder, null) })
                    DropdownMenuItem({ Text(if (item.favorite) "取消收藏" else "收藏") }, { menu = false; favorite() }, leadingIcon = { Icon(Icons.Rounded.Star, null) })
                    DropdownMenuItem({ Text(if (item.pinned) "取消置顶" else "置顶") }, { menu = false; pin() }, leadingIcon = { Icon(Icons.Rounded.PushPin, null) })
                    DropdownMenuItem({ Text("删除", color = MaterialTheme.colorScheme.error) }, { menu = false; delete() }, leadingIcon = { Icon(Icons.Rounded.Delete, null, tint = MaterialTheme.colorScheme.error) })
                }
            }
        }
    }
}

@Composable
private fun SelectionActionBar(
    count: Int,
    clear: () -> Unit,
    favorite: () -> Unit,
    unfavorite: () -> Unit,
    pin: () -> Unit,
    unpin: () -> Unit,
    group: () -> Unit,
    delete: () -> Unit,
) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        item { AssistChip(onClick = clear, label = { Text("已选 $count · 完成") }) }
        item { AssistChip(onClick = favorite, leadingIcon = { Icon(Icons.Rounded.Star, null, Modifier.size(16.dp)) }, label = { Text("收藏") }) }
        item { AssistChip(onClick = unfavorite, label = { Text("取消收藏") }) }
        item { AssistChip(onClick = pin, leadingIcon = { Icon(Icons.Rounded.PushPin, null, Modifier.size(16.dp)) }, label = { Text("置顶") }) }
        item { AssistChip(onClick = unpin, label = { Text("取消置顶") }) }
        item { AssistChip(onClick = group, leadingIcon = { Icon(Icons.Rounded.Folder, null, Modifier.size(16.dp)) }, label = { Text("分组") }) }
        item { AssistChip(onClick = delete, leadingIcon = { Icon(Icons.Rounded.Delete, null, Modifier.size(16.dp)) }, label = { Text("删除") }) }
    }
}

@Composable
private fun EmptyState(title: String, subtitle: String) = Box(Modifier.fillMaxWidth().fillMaxHeight(0.7f), contentAlignment = Alignment.Center) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(Icons.Rounded.Shield, null, tint = GlassBorder, modifier = Modifier.size(52.dp))
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(subtitle, color = TextMuted, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun SettingsScreen(
    autoLock: Int,
    onAutoLock: (Int) -> Unit,
    accountSort: AccountSortPreference,
    passwordSort: PasswordSortPreference,
    onAccountSort: (AccountSortPreference) -> Unit,
    onPasswordSort: (PasswordSortPreference) -> Unit,
    onChangePassword: () -> Unit,
    onImport: () -> Unit,
    onImportUri: () -> Unit,
    onGoogleExport: () -> Unit,
    onExport: (Boolean) -> Unit,
    groups: List<GroupRow>,
    passwordGroups: List<GroupRow>,
    viewModel: AppViewModel,
) {
    var sortTarget by remember { mutableStateOf<String?>(null) }
    var selectedMinutes by remember { mutableIntStateOf(autoLock) }
    var groupName by remember { mutableStateOf("") }
    var passwordGroupName by remember { mutableStateOf("") }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
        contentPadding = PaddingValues(top = 12.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { SettingsSection("安全") {
            SettingsAction(Icons.Rounded.Lock, "修改主密码", "重新包装数据密钥，不重新加密全部记录", onChangePassword)
            Text("自动锁定", fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 8.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                items(listOf(0, 1, 5, 15, 30)) { minutes ->
                    FilterChip(
                        selected = selectedMinutes == minutes,
                        onClick = { selectedMinutes = minutes; onAutoLock(minutes) },
                        label = { Text(if (minutes == 0) "关闭" else "$minutes 分钟") },
                    )
                }
            }
        } }
        item { SettingsSection("列表排序") {
            SettingsAction(Icons.AutoMirrored.Rounded.Sort, "验证码排序", accountSort.summary) {
                sortTarget = "accounts"
            }
            SettingsAction(Icons.AutoMirrored.Rounded.Sort, "密码本排序", passwordSort.summary) {
                sortTarget = "passwords"
            }
        } }
        item { SettingsSection("备份与迁移") {
            SettingsAction(Icons.Rounded.FileUpload, "导入数据", "自动识别加密备份、JSON 和 URI", onImport)
            SettingsAction(Icons.Rounded.QrCodeScanner, "粘贴 otpauth URI", "直接导入单条验证码或 Google 迁移 URI", onImportUri)
            SettingsAction(Icons.Rounded.FileDownload, "加密备份", "推荐，跨设备时使用主密码恢复") { onExport(true) }
            SettingsAction(Icons.Rounded.FileDownload, "明文 JSON", "文件将直接包含密钥和密码") { onExport(false) }
            SettingsAction(
                Icons.Rounded.QrCodeScanner,
                "Google Authenticator 二维码",
                "生成迁移二维码供另一台设备扫描",
                onGoogleExport,
            )
        } }
        item { SettingsSection("验证码分组") {
            GroupQuickManager(groups, "default", groupName, { groupName = it }, { viewModel.createGroup(groupName); groupName = "" }, viewModel::renameGroup, viewModel::deleteGroup)
        } }
        item { SettingsSection("密码本分组") {
            GroupQuickManager(passwordGroups, "password-default", passwordGroupName, { passwordGroupName = it }, { viewModel.createPasswordGroup(passwordGroupName); passwordGroupName = "" }, viewModel::renamePasswordGroup, viewModel::deletePasswordGroup)
        } }
        item { SettingsSection("关于") {
            Text("验证器 1.4.20", fontWeight = FontWeight.SemiBold)
            Text("离线生成验证码并管理本地密码。数据不会上传云端。", color = TextMuted, style = MaterialTheme.typography.bodySmall)
        } }
    }
    when (sortTarget) {
        "accounts" -> SortSettingsDialog(
            title = "验证码排序",
            fields = AccountSortField.entries.map { it.value to it.label },
            selectedField = accountSort.sortField.value,
            selectedDirection = accountSort.direction,
            onClose = { sortTarget = null },
            onConfirm = { field, direction ->
                onAccountSort(AccountSortPreference(AccountSortField.fromValue(field), direction))
                sortTarget = null
            },
        )
        "passwords" -> SortSettingsDialog(
            title = "密码本排序",
            fields = PasswordSortField.entries.map { it.value to it.label },
            selectedField = passwordSort.sortField.value,
            selectedDirection = passwordSort.direction,
            onClose = { sortTarget = null },
            onConfirm = { field, direction ->
                onPasswordSort(PasswordSortPreference(PasswordSortField.fromValue(field), direction))
                sortTarget = null
            },
        )
    }
}

private fun isSafeWebUrl(value: String): Boolean {
    val scheme = runCatching { Uri.parse(value).scheme?.lowercase() }.getOrNull()
    return scheme == "http" || scheme == "https"
}

@Composable
private fun SortSettingsDialog(
    title: String,
    fields: List<Pair<String, String>>,
    selectedField: String,
    selectedDirection: MobileSortDirection,
    onClose: () -> Unit,
    onConfirm: (String, MobileSortDirection) -> Unit,
) {
    var field by remember(title, selectedField) { mutableStateOf(selectedField) }
    var direction by remember(title, selectedDirection) { mutableStateOf(selectedDirection) }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("排序字段", fontWeight = FontWeight.Medium)
                fields.forEach { (value, label) ->
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable {
                            field = value
                            direction = if (value == "created") {
                                MobileSortDirection.DESCENDING
                            } else {
                                MobileSortDirection.ASCENDING
                            }
                        }.padding(vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = field == value, onClick = null)
                        Text(label)
                    }
                }
                HorizontalDivider(color = GlassBorder, modifier = Modifier.padding(vertical = 4.dp))
                Text("排序方向", fontWeight = FontWeight.Medium)
                MobileSortDirection.entries.forEach { option ->
                    val label = when (option) {
                        MobileSortDirection.ASCENDING -> if (field == "created") "最早优先" else "升序"
                        MobileSortDirection.DESCENDING -> if (field == "created") "最新优先" else "降序"
                    }
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable {
                            direction = option
                        }.padding(vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = direction == option, onClick = null)
                        Text(label)
                    }
                }
            }
        },
        confirmButton = { Button(onClick = { onConfirm(field, direction) }) { Text("确定") } },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
    )
}

@Composable
private fun SettingsSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(shape = RoundedCornerShape(8.dp), colors = CardDefaults.cardColors(containerColor = GlassSurface), border = androidx.compose.foundation.BorderStroke(1.dp, GlassBorder)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            HorizontalDivider(color = GlassBorder)
            content()
        }
    }
}

@Composable
private fun SettingsAction(icon: ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(onClick = onClick).padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = AccentBlue)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) { Text(title, fontWeight = FontWeight.Medium); Text(subtitle, color = TextMuted, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun GroupQuickManager(
    groups: List<GroupRow>, defaultId: String, name: String, onName: (String) -> Unit, onAdd: () -> Unit,
    onRename: (String, String) -> Unit, onDelete: (String) -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(name, onName, placeholder = { Text("新分组名称") }, singleLine = true, modifier = Modifier.weight(1f))
        Button(onClick = onAdd, enabled = name.isNotBlank()) { Text("添加") }
    }
    groups.filterNot { it.id == defaultId }.forEach { group ->
        var editing by remember(group.id) { mutableStateOf(false) }
        var editedName by remember(group.id) { mutableStateOf(group.name) }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (editing) OutlinedTextField(editedName, { editedName = it }, singleLine = true, modifier = Modifier.weight(1f))
            else Text(group.name, modifier = Modifier.weight(1f))
            IconButton(onClick = { if (editing) { onRename(group.id, editedName); editing = false } else editing = true }) { Icon(Icons.Rounded.Edit, "重命名") }
            IconButton(onClick = { onDelete(group.id) }) { Icon(Icons.Rounded.Delete, "删除", tint = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun PasswordInputDialog(title: String, onClose: () -> Unit, onSubmit: (String) -> Unit) {
    var password by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = { OutlinedTextField(password, { password = it }, visualTransformation = PasswordVisualTransformation(), label = { Text("主密码") }, singleLine = true) },
        confirmButton = { Button(onClick = { onSubmit(password) }, enabled = password.isNotBlank()) { Text("解密并导入") } },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
    )
}

private fun googleAuthenticatorQrBitmap(content: String, size: Int): Bitmap {
    val hints: Map<EncodeHintType, Any> = mapOf(
        EncodeHintType.CHARACTER_SET to "UTF-8",
        EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.L,
        EncodeHintType.MARGIN to 4,
    )
    val matrix = QRCodeWriter().encode(content, BarcodeFormat.QR_CODE, size, size, hints)
    val pixels = IntArray(size * size)
    for (y in 0 until size) {
        val row = y * size
        for (x in 0 until size) {
            pixels[row + x] = if (matrix[x, y]) 0xFF000000.toInt() else 0xFFFFFFFF.toInt()
        }
    }
    return Bitmap.createBitmap(pixels, size, size, Bitmap.Config.ARGB_8888)
}

@Composable
private fun GoogleAuthenticatorExportDialog(export: JSONObject, onClose: () -> Unit) {
    val uris = export.getJSONArray("uris").strings()
    val warnings = export.optJSONArray("warnings")?.strings().orEmpty()
    var page by remember(export) { mutableIntStateOf(0) }
    AlertDialog(
        onDismissRequest = onClose,
        title = {
            Column {
                Text("Google Authenticator")
                Text(
                    "${export.optInt("accounts_exported")} 个账号 · 第 ${page + 1}/${uris.size} 张",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted,
                )
            }
        },
        text = {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                val imageSize = if (maxWidth > 420.dp) 420.dp else maxWidth
                val imagePixels = with(LocalDensity.current) {
                    imageSize.roundToPx().coerceIn(320, 1_200)
                }
                val bitmap = remember(uris[page], imagePixels) {
                    googleAuthenticatorQrBitmap(uris[page], imagePixels)
                }
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Image(
                        bitmap = bitmap.asImageBitmap(),
                        contentDescription = "Google Authenticator 导入二维码，第 ${page + 1} 张",
                        modifier = Modifier.size(imageSize).background(Color.White),
                        filterQuality = FilterQuality.None,
                    )
                    Text(
                        "二维码包含账号密钥，请只允许可信设备扫描。",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted,
                    )
                    if (warnings.isNotEmpty()) {
                        HorizontalDivider(color = GlassBorder)
                        Text(
                            "已跳过 ${warnings.size} 个不兼容账号",
                            style = MaterialTheme.typography.labelLarge,
                            color = WarmOrange,
                        )
                        warnings.take(2).forEach { warning ->
                            Text(
                                warning,
                                style = MaterialTheme.typography.bodySmall,
                                color = TextMuted,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.End,
            ) {
                IconButton(onClick = { page -= 1 }, enabled = page > 0) {
                    Icon(Icons.Rounded.ChevronLeft, "上一张")
                }
                TextButton(onClick = onClose) { Text("关闭") }
                IconButton(onClick = { page += 1 }, enabled = page + 1 < uris.size) {
                    Icon(Icons.Rounded.ChevronRight, "下一张")
                }
            }
        },
    )
}

@Composable
private fun SecretDialog(title: String, password: String, onClose: () -> Unit, onCopy: () -> Unit) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = {
            Surface(shape = RoundedCornerShape(8.dp), color = GlassMuted, modifier = Modifier.fillMaxWidth()) {
                Text(password, modifier = Modifier.padding(16.dp), style = MaterialTheme.typography.titleMedium)
            }
        },
        confirmButton = { Button(onClick = onCopy) { Icon(Icons.Rounded.ContentCopy, null); Spacer(Modifier.width(8.dp)); Text("复制密码") } },
        dismissButton = { TextButton(onClick = onClose) { Text("关闭") } },
    )
}

@Composable
private fun ConfirmDialog(
    title: String,
    message: String,
    onClose: () -> Unit,
    confirmLabel: String = "删除",
    onConfirm: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = { Button(onClick = onConfirm) { Text(confirmLabel) } },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
    )
}
