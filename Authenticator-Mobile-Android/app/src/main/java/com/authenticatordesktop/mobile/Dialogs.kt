package com.authenticatordesktop.mobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject

@Composable
private fun DialogActions(onClose: () -> Unit, enabled: Boolean = true, onSave: () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextButton(onClick = onClose) { Text("取消") }
        Button(onClick = onSave, enabled = enabled) { Text("保存") }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountEditorDialog(
    initial: JSONObject? = null,
    groups: List<GroupRow>,
    onClose: () -> Unit,
    onSave: (JSONObject) -> Unit,
) {
    var issuer by remember(initial) { mutableStateOf(initial?.optString("issuer") ?: "") }
    var account by remember(initial) { mutableStateOf(initial?.optString("account") ?: "") }
    var secret by remember(initial) { mutableStateOf(initial?.optString("secret") ?: "") }
    var otpType by remember(initial) { mutableStateOf(initial?.optString("otp_type", "totp") ?: "totp") }
    var counter by remember(initial) { mutableStateOf((initial?.optInt("counter", 0) ?: 0).toString()) }
    var period by remember(initial) { mutableStateOf((initial?.optInt("period", 30) ?: 30).toString()) }
    var digits by remember(initial) { mutableStateOf((initial?.optInt("digits", 6) ?: 6).toString()) }
    var favorite by remember(initial) { mutableStateOf(initial?.optBoolean("favorite") ?: false) }
    var pinned by remember(initial) { mutableStateOf(initial?.optBoolean("pinned") ?: false) }
    var typeExpanded by remember { mutableStateOf(false) }
    val initialGroups = initial?.optJSONArray("group_ids")?.strings()?.toSet() ?: setOf("default")
    var selectedGroups by remember(initial) { mutableStateOf(initialGroups) }
    val labels = mapOf("totp" to "基于时间 (TOTP)", "hotp" to "基于计数器 (HOTP)", "steam" to "Steam 令牌", "battle" to "Battle.net")

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(if (initial == null) "新增验证码" else "编辑验证码") },
        text = {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 560.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item { OutlinedTextField(issuer, { issuer = it }, label = { Text("服务商") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(account, { account = it }, label = { Text("账号") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(secret, { secret = it }, label = { Text("密钥 *") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item {
                    ExposedDropdownMenuBox(expanded = typeExpanded, onExpandedChange = { typeExpanded = !typeExpanded }) {
                        OutlinedTextField(
                            labels[otpType].orEmpty(), {}, readOnly = true,
                            label = { Text("验证码类型") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(typeExpanded) },
                            modifier = Modifier
                                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
                                .fillMaxWidth(),
                        )
                        ExposedDropdownMenu(expanded = typeExpanded, onDismissRequest = { typeExpanded = false }) {
                            labels.forEach { (value, label) ->
                                DropdownMenuItem(text = { Text(label) }, onClick = { otpType = value; typeExpanded = false })
                            }
                        }
                    }
                }
                if (otpType == "hotp") item { OutlinedTextField(counter, { counter = it.filter(Char::isDigit) }, label = { Text("计数器") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                if (otpType != "hotp") item { OutlinedTextField(period, { period = it.filter(Char::isDigit) }, label = { Text("周期（秒）") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(digits, { digits = it.filter(Char::isDigit) }, label = { Text("位数") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { GeneratorToggle("收藏", favorite) { favorite = it } }
                item { GeneratorToggle("置顶", pinned) { pinned = it } }
                item { Text("分组", style = MaterialTheme.typography.labelLarge) }
                items(groups) { group ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = group.id == "default" || group.id in selectedGroups,
                            enabled = group.id != "default",
                            onCheckedChange = { checked ->
                                selectedGroups = if (checked) selectedGroups + group.id else selectedGroups - group.id
                            },
                        )
                        Text(group.name)
                    }
                }
            }
        },
        confirmButton = {
            DialogActions(onClose, secret.isNotBlank()) {
                val result = JSONObject().apply {
                    initial?.let { put("id", it.optString("id")); put("created_at", it.optString("created_at")) }
                    put("issuer", issuer); put("account", account); put("secret", secret)
                    put("otp_type", otpType); put("secret_encoding", initial?.optString("secret_encoding", "base32") ?: "base32")
                    put("counter", counter.toLongOrNull() ?: 0L); put("period", period.toIntOrNull() ?: 30)
                    put("digits", digits.toIntOrNull() ?: 6); put("algorithm", initial?.optString("algorithm", "SHA1") ?: "SHA1")
                    put("favorite", favorite); put("pinned", pinned)
                    put("group_ids", JSONArray((selectedGroups + "default").toList()))
                }
                onSave(result)
            }
        },
    )
}

@Composable
fun PasswordEditorDialog(
    initial: JSONObject? = null,
    groups: List<GroupRow>,
    generatedPassword: ((JSONObject, (String) -> Unit) -> Unit),
    onClose: () -> Unit,
    onSave: (JSONObject) -> Unit,
) {
    var name by remember(initial) { mutableStateOf(initial?.optString("name") ?: "") }
    var username by remember(initial) { mutableStateOf(initial?.optString("username") ?: "") }
    var password by remember(initial) { mutableStateOf(initial?.optString("password") ?: "") }
    var url by remember(initial) { mutableStateOf(initial?.optString("url") ?: "") }
    var notes by remember(initial) { mutableStateOf(initial?.optString("notes") ?: "") }
    var pinned by remember(initial) { mutableStateOf(initial?.optBoolean("pinned") ?: false) }
    var favorite by remember(initial) { mutableStateOf(initial?.optBoolean("favorite") ?: false) }
    var reveal by remember { mutableStateOf(false) }
    var generatorExpanded by remember { mutableStateOf(false) }
    var generatorLength by remember { mutableStateOf("20") }
    var useLowercase by remember { mutableStateOf(true) }
    var useUppercase by remember { mutableStateOf(true) }
    var useDigits by remember { mutableStateOf(true) }
    var useSymbols by remember { mutableStateOf(true) }
    var excludeAmbiguous by remember { mutableStateOf(true) }
    var selectedGroups by remember(initial) {
        mutableStateOf(initial?.optJSONArray("group_ids")?.strings()?.toSet() ?: setOf("password-default"))
    }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(if (initial == null) "新增密码" else "编辑密码") },
        text = {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 580.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item { OutlinedTextField(name, { name = it }, label = { Text("名称/服务（选填）") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(username, { username = it }, label = { Text("用户名 *") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item {
                    OutlinedTextField(
                        password, { password = it }, label = { Text("密码 *") }, singleLine = true,
                        visualTransformation = if (reveal) VisualTransformation.None else PasswordVisualTransformation(),
                        trailingIcon = { TextButton(onClick = { reveal = !reveal }) { Text(if (reveal) "隐藏" else "显示") } },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = generatorExpanded, onClick = { generatorExpanded = !generatorExpanded }, label = { Text("安全密码生成器") })
                    }
                }
                if (generatorExpanded) {
                    item { OutlinedTextField(generatorLength, { generatorLength = it.filter(Char::isDigit) }, label = { Text("长度（8-128）") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                    item { GeneratorToggle("小写字母", useLowercase) { useLowercase = it } }
                    item { GeneratorToggle("大写字母", useUppercase) { useUppercase = it } }
                    item { GeneratorToggle("数字", useDigits) { useDigits = it } }
                    item { GeneratorToggle("符号", useSymbols) { useSymbols = it } }
                    item { GeneratorToggle("排除易混淆字符", excludeAmbiguous) { excludeAmbiguous = it } }
                    item {
                        Button(
                            enabled = (generatorLength.toIntOrNull() ?: 0) in 8..128 && (useLowercase || useUppercase || useDigits || useSymbols),
                            onClick = {
                                val options = JSONObject()
                                    .put("length", generatorLength.toIntOrNull() ?: 20)
                                    .put("lowercase", useLowercase)
                                    .put("uppercase", useUppercase)
                                    .put("digits", useDigits)
                                    .put("symbols", useSymbols)
                                    .put("exclude_ambiguous", excludeAmbiguous)
                                generatedPassword(options) { password = it; reveal = true }
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("生成并填入") }
                    }
                }
                item { OutlinedTextField(url, { url = it }, label = { Text("网址") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(notes, { notes = it }, label = { Text("备注") }, minLines = 3, modifier = Modifier.fillMaxWidth()) }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Text("收藏", modifier = Modifier.weight(1f)); Switch(favorite, { favorite = it })
                    }
                }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Text("置顶", modifier = Modifier.weight(1f)); Switch(pinned, { pinned = it })
                    }
                }
                item { Text("分组", style = MaterialTheme.typography.labelLarge) }
                items(groups) { group ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = group.id == "password-default" || group.id in selectedGroups,
                            enabled = group.id != "password-default",
                            onCheckedChange = { checked -> selectedGroups = if (checked) selectedGroups + group.id else selectedGroups - group.id },
                        )
                        Text(group.name)
                    }
                }
            }
        },
        confirmButton = {
            DialogActions(onClose, username.isNotBlank() && password.isNotBlank()) {
                onSave(
                    JSONObject().apply {
                        put("name", name); put("username", username); put("password", password); put("url", url)
                        put("notes", notes); put("favorite", favorite); put("pinned", pinned)
                        put("group_ids", JSONArray((selectedGroups + "password-default").toList()))
                    },
                )
            }
        },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ServerEditorDialog(
    initial: JSONObject? = null,
    onPickPrivateKey: ((String) -> Unit) -> Unit,
    onClose: () -> Unit,
    onSave: (JSONObject) -> Unit,
) {
    var name by remember(initial) { mutableStateOf(initial?.optString("name") ?: "") }
    var host by remember(initial) { mutableStateOf(initial?.optString("host") ?: "") }
    var port by remember(initial) { mutableStateOf((initial?.optInt("port", 22) ?: 22).toString()) }
    var username by remember(initial) { mutableStateOf(initial?.optString("username") ?: "") }
    var authKind by remember(initial) { mutableStateOf(initial?.optString("auth_kind", "password") ?: "password") }
    var password by remember { mutableStateOf("") }
    var privateKey by remember { mutableStateOf("") }
    var privateKeyPassphrase by remember { mutableStateOf("") }
    var notes by remember(initial) { mutableStateOf(initial?.optString("notes") ?: "") }
    var replaceCredentials by remember(initial) { mutableStateOf(initial == null) }
    var authExpanded by remember { mutableStateOf(false) }
    val needsCredentials = initial == null || replaceCredentials
    val credentialsValid = when (authKind) {
        "private_key" -> privateKey.isNotBlank()
        else -> password.isNotBlank()
    }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(if (initial == null) "新增服务器" else "编辑服务器") },
        text = {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 580.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item { OutlinedTextField(name, { name = it }, label = { Text("名称 *") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(host, { host = it }, label = { Text("IP 或域名 *") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(port, { port = it.filter(Char::isDigit) }, label = { Text("SSH 端口") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(username, { username = it }, label = { Text("用户名 *") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                if (initial != null) item {
                    GeneratorToggle("更新认证资料", replaceCredentials) { enabled ->
                        replaceCredentials = enabled
                        if (enabled) {
                            password = ""
                            privateKey = ""
                            privateKeyPassphrase = ""
                        }
                    }
                }
                item {
                    ExposedDropdownMenuBox(
                        expanded = authExpanded,
                        onExpandedChange = { if (needsCredentials) authExpanded = !authExpanded },
                    ) {
                        OutlinedTextField(
                            value = if (authKind == "private_key") "私钥" else "密码",
                            onValueChange = {},
                            label = { Text("认证方式") },
                            readOnly = true,
                            enabled = needsCredentials,
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(authExpanded) },
                            modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
                        )
                        ExposedDropdownMenu(expanded = authExpanded, onDismissRequest = { authExpanded = false }) {
                            DropdownMenuItem(text = { Text("密码") }, onClick = { authKind = "password"; authExpanded = false })
                            DropdownMenuItem(text = { Text("私钥") }, onClick = { authKind = "private_key"; authExpanded = false })
                        }
                    }
                }
                if (needsCredentials && authKind == "password") item {
                    OutlinedTextField(
                        password,
                        { password = it },
                        label = { Text("SSH 密码 *") },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                if (needsCredentials && authKind == "private_key") {
                    item {
                        OutlinedButton(onClick = { onPickPrivateKey { privateKey = it } }, modifier = Modifier.fillMaxWidth()) {
                            Text(if (privateKey.isBlank()) "导入私钥文件" else "已选择私钥文件")
                        }
                    }
                    item {
                        OutlinedTextField(
                            privateKeyPassphrase,
                            { privateKeyPassphrase = it },
                            label = { Text("私钥口令（如有）") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                item { OutlinedTextField(notes, { notes = it }, label = { Text("备注") }, minLines = 3, modifier = Modifier.fillMaxWidth()) }
            }
        },
        confirmButton = {
            DialogActions(
                onClose,
                name.trim().isNotBlank() && host.trim().isNotBlank() && username.trim().isNotBlank() &&
                    (port.toIntOrNull() ?: 0) in 1..65_535 && (!needsCredentials || credentialsValid),
            ) {
                onSave(
                    JSONObject().apply {
                        initial?.let { put("id", it.optString("id")) }
                        put("name", name)
                        put("host", host)
                        put("port", port.toIntOrNull() ?: 22)
                        put("username", username)
                        put("auth_kind", authKind)
                        put("password", password)
                        put("private_key", privateKey)
                        put("private_key_passphrase", privateKeyPassphrase)
                        put("notes", notes)
                        put("replace_credentials", replaceCredentials)
                    },
                )
            }
        },
    )
}

@Composable
private fun GeneratorToggle(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
fun MasterPasswordDialog(
    title: String,
    requireCurrent: Boolean,
    onClose: (() -> Unit)?,
    onSubmit: (String, String) -> Unit,
) {
    var current by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = { onClose?.invoke() },
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (requireCurrent) OutlinedTextField(current, { current = it }, label = { Text("当前主密码") }, visualTransformation = PasswordVisualTransformation(), singleLine = true)
                OutlinedTextField(password, { password = it }, label = { Text(if (requireCurrent) "新主密码" else "主密码") }, visualTransformation = PasswordVisualTransformation(), singleLine = true)
                if (!requireCurrent || title.contains("创建")) {
                    OutlinedTextField(confirmation, { confirmation = it }, label = { Text("确认主密码") }, visualTransformation = PasswordVisualTransformation(), singleLine = true)
                }
                Text("至少 8 个字符。忘记主密码且设备凭据失效后，数据无法恢复。", style = MaterialTheme.typography.bodySmall, color = TextMuted)
            }
        },
        confirmButton = {
            Button(
                enabled = password.length >= 8 && (confirmation.isEmpty() || confirmation == password),
                onClick = { onSubmit(current, password) },
            ) { Text("确认") }
        },
        dismissButton = { onClose?.let { TextButton(onClick = it) { Text("取消") } } },
    )
}

@Composable
fun UriImportDialog(onClose: () -> Unit, onImport: (String) -> Unit) {
    var uri by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("导入 otpauth URI") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("粘贴标准 otpauth:// URI 或 Google Authenticator 迁移 URI。", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(
                    value = uri,
                    onValueChange = { uri = it },
                    label = { Text("URI") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(onClick = { onImport(uri.trim()) }, enabled = uri.trim().isNotBlank()) { Text("导入") }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
    )
}

@Composable
fun GroupAssignmentDialog(
    title: String,
    groups: List<GroupRow>,
    selected: List<String>,
    defaultId: String,
    onClose: () -> Unit,
    onSave: (List<String>) -> Unit,
) {
    var values by remember { mutableStateOf(selected.toSet() + defaultId) }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = {
            LazyColumn {
                items(groups) { group ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = group.id == defaultId || group.id in values,
                            enabled = group.id != defaultId,
                            onCheckedChange = { checked -> values = if (checked) values + group.id else values - group.id },
                        )
                        Text(group.name)
                    }
                }
            }
        },
        confirmButton = { DialogActions(onClose) { onSave(values.toList()) } },
    )
}
