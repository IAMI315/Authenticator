@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.authenticatordesktop.mobile

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Computer
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.Key
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Terminal
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun ServerScreen(
    state: AppState,
    viewModel: AppViewModel,
    onCreate: () -> Unit,
    onEdit: (ServerRow) -> Unit,
    onDelete: (ServerRow) -> Unit,
) {
    val profiles = state.snapshot.servers
    val sessions = state.serverTerminalSessions
    var expandedProfileId by remember { mutableStateOf<String?>(null) }
    var activeTerminalId by remember { mutableStateOf<String?>(null) }
    var knownTerminalIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    val activeTerminal = sessions.firstOrNull { it.id == activeTerminalId }
    val terminalProfileId = activeTerminal?.profileId
    val activeTerminalProfile = terminalProfileId?.let { profileId -> profiles.firstOrNull { it.id == profileId } }

    LaunchedEffect(profiles) {
        if (expandedProfileId != null && profiles.none { it.id == expandedProfileId }) {
            expandedProfileId = null
            activeTerminalId = null
        }
    }
    LaunchedEffect(sessions.map { it.id }) {
        val currentIds = sessions.mapTo(linkedSetOf()) { it.id }
        sessions.lastOrNull { it.id !in knownTerminalIds }?.let { session ->
            expandedProfileId = session.profileId
        }
        if (activeTerminalId != null && activeTerminalId !in currentIds) activeTerminalId = null
        knownTerminalIds = currentIds
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.weight(1f)) {
                Text("服务器", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                Text("SSH 档案与终端", style = MaterialTheme.typography.bodySmall, color = TextMuted)
            }
            OutlinedButton(onClick = onCreate) {
                Icon(Icons.Rounded.Add, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("新增")
            }
        }

        if (profiles.isEmpty()) {
            EmptyServers(onCreate)
        } else if (activeTerminal != null && activeTerminalProfile != null) {
            ServerTerminalWorkspace(
                profile = activeTerminalProfile,
                sessions = sessions.filter { it.profileId == activeTerminalProfile.id },
                activeSession = activeTerminal,
                onConnect = { viewModel.connectServer(activeTerminalProfile.id) },
                onEdit = { onEdit(activeTerminalProfile) },
                onDelete = { onDelete(activeTerminalProfile) },
                onResetTrust = { viewModel.resetServerHostKey(activeTerminalProfile.id) },
                onShowDetails = {
                    activeTerminalId = null
                    expandedProfileId = activeTerminalProfile.id
                },
                onShowTerminal = { sessionId -> activeTerminalId = sessionId },
                onCloseTerminal = { sessionId ->
                    viewModel.disconnectTerminal(sessionId)
                    if (activeTerminalId == sessionId) activeTerminalId = null
                },
                onCollapse = {
                    activeTerminalId = null
                    expandedProfileId = null
                },
                onReconnect = { viewModel.connectServer(activeTerminalProfile.id) },
                onSendTerminal = viewModel::sendTerminalInput,
                onResizeTerminal = viewModel::resizeTerminal,
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(profiles, key = { it.id }) { profile ->
                    val profileSessions = sessions.filter { it.profileId == profile.id }
                    ServerAccordion(
                        profile = profile,
                        sessions = profileSessions,
                        expanded = expandedProfileId == profile.id,
                        onToggleExpanded = {
                            val expanding = expandedProfileId != profile.id
                            expandedProfileId = if (expanding) profile.id else null
                        },
                        onConnect = { viewModel.connectServer(profile.id) },
                        onEdit = { onEdit(profile) },
                        onDelete = { onDelete(profile) },
                        onResetTrust = { viewModel.resetServerHostKey(profile.id) },
                        onShowTerminal = { sessionId ->
                            expandedProfileId = profile.id
                            activeTerminalId = sessionId
                        },
                        onCloseTerminal = viewModel::disconnectTerminal,
                    )
                }
            }
        }
    }

    sessions.firstOrNull { it.hostKeyPrompt != null }?.let { session ->
        val prompt = session.hostKeyPrompt ?: return@let
        AlertDialog(
            onDismissRequest = { viewModel.rejectServerHostKey(session.id) },
            icon = { Icon(Icons.Rounded.Warning, null, tint = WarmOrange) },
            title = { Text("确认服务器主机指纹") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${session.username}@${session.host}:${session.port}")
                    Text(prompt.algorithm, style = MaterialTheme.typography.labelMedium, color = TextMuted)
                    SelectionContainer { Text(prompt.fingerprint, fontFamily = FontFamily.Monospace) }
                    Text("仅在确认这是目标服务器时继续。主机密钥变更会被阻止并需要重新确认。", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                }
            },
            confirmButton = { Button(onClick = { viewModel.approveServerHostKey(session.id) }) { Text("信任并连接") } },
            dismissButton = { TextButton(onClick = { viewModel.rejectServerHostKey(session.id) }) { Text("拒绝") } },
        )
    }
}

@Composable
private fun EmptyServers(onCreate: () -> Unit) = Box(
    modifier = Modifier.fillMaxSize(),
    contentAlignment = Alignment.Center,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primaryContainer) {
            Icon(Icons.Rounded.Computer, null, tint = AccentBlue, modifier = Modifier.padding(16.dp).size(36.dp))
        }
        Text("尚未添加服务器", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Text("服务器凭据会加密保存在本机保险库中。", color = TextMuted, style = MaterialTheme.typography.bodySmall)
        Button(onClick = onCreate) { Text("新增服务器") }
    }
}

@Composable
private fun ServerAccordion(
    profile: ServerRow,
    sessions: List<AndroidTerminalSession>,
    expanded: Boolean,
    onToggleExpanded: () -> Unit,
    onConnect: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onResetTrust: () -> Unit,
    onShowTerminal: (String) -> Unit,
    onCloseTerminal: (String) -> Unit,
) {
    val connecting = sessions.any { it.status in setOf("connecting", "awaiting_host_key") }
    val container = if (expanded) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f) else GlassSurface
    Surface(
        modifier = Modifier.fillMaxWidth().animateContentSize(),
        shape = RoundedCornerShape(8.dp),
        color = container,
        border = BorderStroke(1.dp, if (expanded) AccentBlue.copy(alpha = 0.35f) else GlassBorder),
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 6.dp, top = 10.dp, bottom = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Rounded.Computer, null, tint = AccentBlue, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(profile.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        "${profile.username}@${profile.host}:${profile.port}",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Button(
                    onClick = onConnect,
                    enabled = profile.credentialsConfigured && !connecting,
                    modifier = Modifier.heightIn(min = 40.dp),
                ) {
                    Icon(Icons.Rounded.PlayArrow, null, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(2.dp))
                    Text(if (connecting) "连接中" else "连接")
                }
                IconButton(onClick = onToggleExpanded) {
                    Icon(if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, if (expanded) "收起详情" else "展开详情")
                }
            }
            if (expanded) {
                HorizontalDivider(color = GlassBorder)
                if (sessions.isEmpty()) {
                    ServerDetails(profile, connecting, onConnect, onEdit, onDelete, onResetTrust)
                } else {
                    ServerTabs(
                        profile = profile,
                        sessions = sessions,
                        onShowTerminal = onShowTerminal,
                        onCloseTerminal = onCloseTerminal,
                        onConnect = onConnect,
                        onEdit = onEdit,
                        onDelete = onDelete,
                        onResetTrust = onResetTrust,
                    )
                }
            }
        }
    }
}

@Composable
private fun ServerTabs(
    profile: ServerRow,
    sessions: List<AndroidTerminalSession>,
    onShowTerminal: (String) -> Unit,
    onCloseTerminal: (String) -> Unit,
    onConnect: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onResetTrust: () -> Unit,
) {
    ScrollableTabRow(selectedTabIndex = 0, edgePadding = 8.dp, containerColor = Color.Transparent) {
        Tab(selected = true, onClick = {}, text = { Text("详情") })
        sessions.forEach { session ->
            Tab(
                selected = false,
                onClick = { onShowTerminal(session.id) },
                text = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Terminal, null, modifier = Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(terminalTabLabel(session), maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.width(72.dp))
                        IconButton(onClick = { onCloseTerminal(session.id) }, modifier = Modifier.size(28.dp)) {
                            Icon(Icons.Rounded.Close, "关闭终端", modifier = Modifier.size(16.dp))
                        }
                    }
                },
            )
        }
    }
    ServerDetails(
        profile,
        sessions.any { it.status in setOf("connecting", "awaiting_host_key") },
        onConnect,
        onEdit,
        onDelete,
        onResetTrust,
    )
}

private fun terminalTabLabel(session: AndroidTerminalSession): String = when (session.status) {
    "connected" -> "终端"
    "connecting" -> "连接中"
    "awaiting_host_key" -> "待确认"
    "host_key_changed" -> "指纹变化"
    "closed" -> "已关闭"
    else -> "连接失败"
}

/**
 * A terminal is deliberately rendered outside the server LazyColumn. Keeping the output
 * viewport and command line in a fixed parent avoids a nested scrolling layout moving the
 * command line off-screen when the server item expands or the software keyboard opens.
 */
@Composable
private fun ServerTerminalWorkspace(
    profile: ServerRow,
    sessions: List<AndroidTerminalSession>,
    activeSession: AndroidTerminalSession,
    onConnect: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onResetTrust: () -> Unit,
    onShowDetails: () -> Unit,
    onShowTerminal: (String) -> Unit,
    onCloseTerminal: (String) -> Unit,
    onCollapse: () -> Unit,
    onReconnect: () -> Unit,
    onSendTerminal: (String, String) -> Unit,
    onResizeTerminal: (String, Int, Int) -> Unit,
    modifier: Modifier,
) {
    val connecting = sessions.any { it.status in setOf("connecting", "awaiting_host_key") }
    Column(
        modifier = modifier.imePadding(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(8.dp),
            color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f),
            border = BorderStroke(1.dp, AccentBlue.copy(alpha = 0.35f)),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 6.dp, top = 9.dp, bottom = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Rounded.Computer, null, tint = AccentBlue, modifier = Modifier.size(21.dp))
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(profile.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        "${profile.username}@${profile.host}:${profile.port}",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Button(
                    onClick = onConnect,
                    enabled = profile.credentialsConfigured && !connecting,
                    modifier = Modifier.heightIn(min = 40.dp),
                ) {
                    Icon(Icons.Rounded.PlayArrow, null, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(2.dp))
                    Text(if (connecting) "连接中" else "连接")
                }
                IconButton(onClick = onCollapse) {
                    Icon(Icons.Rounded.ExpandLess, "返回服务器列表")
                }
            }
        }

        ScrollableTabRow(
            selectedTabIndex = sessions.indexOfFirst { it.id == activeSession.id }.coerceAtLeast(0) + 1,
            edgePadding = 8.dp,
            containerColor = Color.Transparent,
        ) {
            Tab(selected = false, onClick = onShowDetails, text = { Text("详情") })
            sessions.forEach { session ->
                Tab(
                    selected = session.id == activeSession.id,
                    onClick = { onShowTerminal(session.id) },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.Terminal, null, modifier = Modifier.size(15.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(terminalTabLabel(session), maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.width(70.dp))
                            IconButton(
                                onClick = { onCloseTerminal(session.id) },
                                modifier = Modifier.size(28.dp),
                            ) {
                                Icon(Icons.Rounded.Close, "关闭终端", modifier = Modifier.size(16.dp))
                            }
                        }
                    },
                )
            }
        }

        TerminalPanel(
            session = activeSession,
            onReconnect = onReconnect,
            onSend = onSendTerminal,
            onResize = onResizeTerminal,
            modifier = Modifier.fillMaxWidth().weight(1f),
        )
    }
}

@Composable
private fun ServerDetails(
    profile: ServerRow,
    connecting: Boolean,
    onConnect: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onResetTrust: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AssistChip(
                onClick = {},
                label = { Text(if (profile.authKind == "private_key") "私钥认证" else "密码认证") },
                leadingIcon = { Icon(Icons.Rounded.Key, null, modifier = Modifier.size(16.dp)) },
            )
            AssistChip(onClick = {}, label = { Text(if (profile.credentialsConfigured) "凭据已配置" else "需要凭据") })
        }
        if (profile.notes.isNotBlank()) Text(profile.notes, style = MaterialTheme.typography.bodySmall, color = TextMuted)
        if (profile.trustedFingerprint.isNotBlank()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "已信任：${profile.trustedFingerprint}",
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.labelSmall,
                    color = FreshGreen,
                )
                TextButton(onClick = onResetTrust) { Text("重置信任") }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onConnect, enabled = profile.credentialsConfigured && !connecting, modifier = Modifier.weight(1f)) {
                Icon(Icons.Rounded.PlayArrow, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text(if (connecting) "正在连接" else "连接")
            }
            OutlinedButton(onClick = onEdit) {
                Icon(Icons.Rounded.Edit, null, modifier = Modifier.size(17.dp))
                Spacer(Modifier.width(3.dp))
                Text("编辑")
            }
            IconButton(onClick = onDelete) { Icon(Icons.Rounded.Delete, "删除服务器", tint = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun TerminalPanel(
    session: AndroidTerminalSession,
    onReconnect: () -> Unit,
    onSend: (String, String) -> Unit,
    onResize: (String, Int, Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    var command by remember(session.id) { mutableStateOf("") }
    val outputScroll = rememberScrollState()
    val shortcutScroll = rememberScrollState()
    val density = LocalDensity.current
    LaunchedEffect(session.output) { outputScroll.scrollTo(outputScroll.maxValue) }
    fun submit() {
        val value = command
        if (value.isBlank() || session.status != "connected") return
        command = ""
        onSend(session.id, "$value\n")
    }
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(Color(0xFF0B1A2B), RoundedCornerShape(8.dp))
            .onSizeChanged { size ->
                // Keep remote line wrapping in sync with the visible native terminal area.
                val characterWidth = with(density) { 8.sp.toPx() }
                val lineHeight = with(density) { 18.dp.toPx() }
                onResize(
                    session.id,
                    (size.width / characterWidth).toInt().coerceIn(24, 240),
                    (size.height / lineHeight).toInt().coerceIn(10, 120),
                )
            },
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                terminalStatusLabel(session.status),
                color = if (session.status == "connected") Color(0xFF74D7B0) else Color(0xFFAFC9E6),
                style = MaterialTheme.typography.labelMedium,
            )
            Spacer(Modifier.weight(1f))
            if (session.status in setOf("error", "closed", "host_key_changed")) {
                TextButton(onClick = onReconnect) {
                    Icon(Icons.Rounded.Refresh, null, tint = Color(0xFFAFC9E6), modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(3.dp))
                    Text("重连", color = Color(0xFFAFC9E6))
                }
            }
        }
        HorizontalDivider(color = Color(0xFF23405E))
        Box(
            modifier = Modifier.weight(1f).fillMaxWidth().verticalScroll(outputScroll).padding(12.dp),
        ) {
            SelectionContainer {
                Text(
                    text = session.output.ifBlank { "正在等待终端输出..." },
                    color = Color(0xFFEAF3FF),
                    fontFamily = FontFamily.Monospace,
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                )
            }
        }
        HorizontalDivider(color = Color(0xFF23405E))
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(shortcutScroll).padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            TerminalKey("Ctrl+C", session.status == "connected") { onSend(session.id, "\u0003") }
            TerminalKey("Esc", session.status == "connected") { onSend(session.id, "\u001B") }
            TerminalKey("Tab", session.status == "connected") { onSend(session.id, "\t") }
            TerminalKey("↑", session.status == "connected") { onSend(session.id, "\u001B[A") }
            TerminalKey("↓", session.status == "connected") { onSend(session.id, "\u001B[B") }
            TerminalKey("←", session.status == "connected") { onSend(session.id, "\u001B[D") }
            TerminalKey("→", session.status == "connected") { onSend(session.id, "\u001B[C") }
        }
        HorizontalDivider(color = Color(0xFF23405E))
        Surface(
            modifier = Modifier.fillMaxWidth().padding(8.dp),
            shape = RoundedCornerShape(6.dp),
            color = Color(0xFF122B44),
            border = BorderStroke(1.dp, Color(0xFF315575)),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "›",
                    color = Color(0xFF77D8B3),
                    fontFamily = FontFamily.Monospace,
                    fontSize = 20.sp,
                    modifier = Modifier.padding(end = 8.dp),
                )
                Box(modifier = Modifier.weight(1f)) {
                    if (command.isEmpty()) {
                        Text(
                            "输入命令",
                            color = Color(0xFF7895B5),
                            fontFamily = FontFamily.Monospace,
                            fontSize = 15.sp,
                        )
                    }
                    BasicTextField(
                        value = command,
                        onValueChange = { command = it },
                        enabled = session.status == "connected",
                        textStyle = TextStyle(
                            color = Color(0xFFF3F8FF),
                            fontFamily = FontFamily.Monospace,
                            fontSize = 15.sp,
                        ),
                        cursorBrush = SolidColor(Color(0xFF77D8B3)),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { submit() }),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = ::submit,
                    enabled = session.status == "connected" && command.isNotBlank(),
                ) { Text("发送") }
            }
        }
    }
}

@Composable
private fun TerminalKey(label: String, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = { if (enabled) onClick() },
        shape = RoundedCornerShape(5.dp),
        color = if (enabled) Color(0xFF18334E) else Color(0xFF13283D),
        border = BorderStroke(1.dp, if (enabled) Color(0xFF315575) else Color(0xFF213B54)),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
            color = if (enabled) Color(0xFFC9DCF1) else Color(0xFF66819E),
            fontFamily = FontFamily.Monospace,
            fontSize = 12.sp,
        )
    }
}

private fun terminalStatusLabel(status: String): String = when (status) {
    "connected" -> "已连接"
    "awaiting_host_key" -> "等待确认主机指纹"
    "connecting" -> "正在连接"
    "host_key_changed" -> "主机指纹已变化"
    "closed" -> "终端已关闭"
    else -> "连接失败"
}
