package com.authenticatordesktop.mobile

import android.util.Base64
import com.jcraft.jsch.ChannelShell
import com.jcraft.jsch.HostKey
import com.jcraft.jsch.HostKeyRepository
import com.jcraft.jsch.JSch
import com.jcraft.jsch.JSchException
import com.jcraft.jsch.Session
import com.jcraft.jsch.UserInfo
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

private const val SSH_CONNECT_TIMEOUT_MILLIS = 15_000
private const val HOST_KEY_DECISION_TIMEOUT_SECONDS = 120L
private const val MAX_TERMINAL_OUTPUT_CHARS = 100_000
private const val MAX_SESSIONS = 8

data class AndroidTrustedHostKey(
    val algorithm: String,
    val keyData: String,
) {
    val fingerprint: String
        get() = "SHA256:" + Base64.encodeToString(
            MessageDigest.getInstance("SHA-256").digest(
                Base64.decode(keyData, Base64.DEFAULT),
            ),
            Base64.NO_WRAP,
        ).trimEnd('=')
}

data class AndroidServerConnection(
    val id: String,
    val name: String,
    val host: String,
    val port: Int,
    val username: String,
    val authKind: String,
    val password: String,
    val privateKey: String,
    val privateKeyPassphrase: String,
    val trustedHostKey: AndroidTrustedHostKey?,
) {
    companion object {
        fun fromJson(value: JSONObject): AndroidServerConnection {
            val trusted = value.optJSONObject("trusted_host_key")?.let {
                AndroidTrustedHostKey(it.optString("algorithm"), it.optString("key_data"))
            }
            return AndroidServerConnection(
                id = value.getString("id"),
                name = value.optString("name"),
                host = value.optString("host"),
                port = value.optInt("port", 22),
                username = value.optString("username"),
                authKind = value.optString("auth_kind", "password"),
                password = value.optString("password"),
                privateKey = value.optString("private_key"),
                privateKeyPassphrase = value.optString("private_key_passphrase"),
                trustedHostKey = trusted,
            )
        }
    }
}

data class AndroidHostKeyPrompt(
    val algorithm: String,
    val keyData: String,
    val fingerprint: String,
)

data class AndroidTerminalSession(
    val id: String,
    val profileId: String,
    val name: String,
    val host: String,
    val port: Int,
    val username: String,
    val status: String = "connecting",
    val output: String = "正在连接服务器...\n",
    val error: String = "",
    val hostKeyPrompt: AndroidHostKeyPrompt? = null,
)

internal class ProfileHostKeyRepository(
    private val trustedHostKey: AndroidTrustedHostKey?,
) : HostKeyRepository {
    override fun check(host: String?, key: ByteArray?): Int {
        if (key == null) return HostKeyRepository.NOT_INCLUDED
        val received = Base64.encodeToString(key, Base64.NO_WRAP)
        return when {
            trustedHostKey == null -> HostKeyRepository.NOT_INCLUDED
            trustedHostKey.keyData == received -> HostKeyRepository.OK
            else -> HostKeyRepository.CHANGED
        }
    }

    override fun add(hostkey: HostKey?, ui: UserInfo?) = Unit
    override fun remove(host: String?, type: String?) = Unit
    override fun remove(host: String?, type: String?, key: ByteArray?) = Unit
    override fun getKnownHostsRepositoryID(): String = "authenticator-mobile"
    override fun getHostKey(): Array<HostKey> = emptyArray()
    // JSch invokes this lookup with a null type while constructing a session.
    override fun getHostKey(host: String?, type: String?): Array<HostKey> = emptyArray()
}

class AndroidSshSessionManager {
    private val lock = Any()
    private val mutableSessions = MutableStateFlow<Map<String, AndroidTerminalSession>>(emptyMap())
    val sessions = mutableSessions.asStateFlow()
    private val controls = mutableMapOf<String, SessionControl>()

    fun connect(connection: AndroidServerConnection): String {
        synchronized(lock) {
            if (controls.values.count { !it.closed } >= MAX_SESSIONS) {
                throw IllegalStateException("最多可同时打开 $MAX_SESSIONS 个 SSH 终端")
            }
        }
        val sessionId = UUID.randomUUID().toString()
        val control = SessionControl(sessionId, connection)
        synchronized(lock) { controls[sessionId] = control }
        update(sessionId) {
            AndroidTerminalSession(
                id = sessionId,
                profileId = connection.id,
                name = connection.name,
                host = connection.host,
                port = connection.port,
                username = connection.username,
            )
        }
        Thread({ runConnection(control) }, "android-ssh-${sessionId.take(8)}").apply {
            isDaemon = true
            start()
        }
        return sessionId
    }

    fun write(sessionId: String, data: String) {
        if (data.toByteArray(StandardCharsets.UTF_8).size > 32_768) {
            throw IllegalArgumentException("单次终端输入过长")
        }
        val control = control(sessionId)
        val stream = synchronized(control) { control.channel?.outputStream }
            ?: throw IllegalStateException("终端尚未连接")
        synchronized(stream) {
            stream.write(data.toByteArray(StandardCharsets.UTF_8))
            stream.flush()
        }
    }

    fun resize(sessionId: String, columns: Int, rows: Int) {
        val control = controlOrNull(sessionId) ?: return
        synchronized(control) {
            control.channel?.setPtySize(columns.coerceIn(20, 500), rows.coerceIn(8, 200), 0, 0)
        }
    }

    fun approveHostKey(sessionId: String) {
        val control = control(sessionId)
        control.hostKeyApproved = true
        control.hostKeyDecision.countDown()
    }

    fun rejectHostKey(sessionId: String) {
        val control = controlOrNull(sessionId) ?: return
        control.hostKeyApproved = false
        control.hostKeyDecision.countDown()
        dismiss(sessionId)
    }

    fun pendingHostKey(sessionId: String): AndroidHostKeyPrompt? =
        mutableSessions.value[sessionId]?.hostKeyPrompt

    fun close(sessionId: String) {
        val control = controlOrNull(sessionId) ?: return
        control.closed = true
        control.hostKeyDecision.countDown()
        synchronized(control) {
            runCatching { control.channel?.disconnect() }
            runCatching { control.session?.disconnect() }
        }
        update(sessionId) { current ->
            current.copy(status = "closed", hostKeyPrompt = null)
        }
    }

    /** Close a terminal at the user's request and remove its tab and output. */
    fun dismiss(sessionId: String) {
        val control = synchronized(lock) { controls.remove(sessionId) }
        if (control != null) {
            control.closed = true
            control.hostKeyDecision.countDown()
            synchronized(control) {
                runCatching { control.channel?.disconnect() }
                runCatching { control.session?.disconnect() }
                control.channel = null
                control.session = null
            }
        }
        synchronized(lock) {
            mutableSessions.value = mutableSessions.value - sessionId
        }
    }

    fun closeProfile(profileId: String) {
        mutableSessions.value.values.filter { it.profileId == profileId }.forEach { dismiss(it.id) }
    }

    fun closeAll() {
        mutableSessions.value.keys.toList().forEach(::close)
    }

    /** Clear terminal output as well as sockets when sensitive data must leave memory. */
    fun clearAll() {
        closeAll()
        synchronized(lock) {
            controls.clear()
            mutableSessions.value = emptyMap()
        }
    }

    private fun runConnection(control: SessionControl) {
        try {
            val profile = control.connection
            val jsch = JSch()
            jsch.setHostKeyRepository(ProfileHostKeyRepository(profile.trustedHostKey))
            if (profile.authKind == "private_key") {
                if (profile.privateKey.isBlank()) throw IllegalArgumentException("请先导入 SSH 私钥")
                jsch.addIdentity(
                    "authenticator-mobile-${profile.id}",
                    profile.privateKey.toByteArray(StandardCharsets.UTF_8),
                    null,
                    profile.privateKeyPassphrase.takeIf(String::isNotBlank)?.toByteArray(StandardCharsets.UTF_8),
                )
            } else if (profile.password.isBlank()) {
                throw IllegalArgumentException("请先设置 SSH 密码")
            }
            val session = jsch.getSession(profile.username, profile.host, profile.port)
            synchronized(control) { control.session = session }
            @Suppress("DEPRECATION")
            if (profile.authKind == "password") session.setPassword(profile.password)
            session.setConfig("StrictHostKeyChecking", "ask")
            session.setConfig("PreferredAuthentications", "publickey,keyboard-interactive,password")
            session.setTimeout(SSH_CONNECT_TIMEOUT_MILLIS)
            session.setUserInfo(
                HostKeyUserInfo(
                    control,
                    profile.trustedHostKey,
                    session,
                    ::setAwaitingHostKey,
                    ::setHostKeyChanged,
                ),
            )
            session.connect(SSH_CONNECT_TIMEOUT_MILLIS)
            if (control.closed) return

            val channel = session.openChannel("shell") as ChannelShell
            channel.setPtyType("xterm-256color")
            channel.setPtySize(100, 28, 0, 0)
            synchronized(control) { control.channel = channel }
            channel.connect(SSH_CONNECT_TIMEOUT_MILLIS)
            setStatus(control.id, "connected")
            val input = channel.inputStream
            val buffer = ByteArray(16_384)
            while (!control.closed && channel.isConnected) {
                val count = input.read(buffer)
                if (count < 0) break
                if (count > 0) appendOutput(control.id, String(buffer, 0, count, StandardCharsets.UTF_8))
            }
        } catch (error: Throwable) {
            if (!control.closed) {
                val message = when {
                    mutableSessions.value[control.id]?.status == "host_key_changed" ->
                        "服务器主机指纹已变化，请重置信任记录后再连接。"
                    error is JSchException && error.message.orEmpty().contains("HostKey has been changed", ignoreCase = true) ->
                        "服务器主机指纹已变化，请重置信任记录后再连接。"
                    error is java.net.SocketTimeoutException -> "连接超时（15 秒），请检查地址、端口和网络。"
                    error is java.net.ConnectException -> "目标主机拒绝连接，请确认 SSH 服务与端口。"
                    error is java.net.UnknownHostException -> "无法解析服务器地址，请检查 IP 或域名。"
                    error is JSchException && error.message.orEmpty().contains("Auth fail", ignoreCase = true) ->
                        "SSH 身份验证失败，请检查用户名、密码或私钥。"
                    else -> error.message?.take(300)?.ifBlank { null } ?: "SSH 连接失败"
                }
                setStatus(control.id, "error", message)
            }
        } finally {
            control.closed = true
            synchronized(control) {
                runCatching { control.channel?.disconnect() }
                runCatching { control.session?.disconnect() }
                control.channel = null
                control.session = null
            }
            update(control.id) { current ->
                if (current.status == "error" || current.status == "host_key_changed") current
                else current.copy(status = "closed", hostKeyPrompt = null)
            }
        }
    }

    private fun setAwaitingHostKey(control: SessionControl, prompt: AndroidHostKeyPrompt) {
        update(control.id) { current -> current.copy(status = "awaiting_host_key", hostKeyPrompt = prompt) }
    }

    private fun setHostKeyChanged(control: SessionControl) {
        setStatus(control.id, "host_key_changed", "服务器主机指纹已变化")
    }

    private fun setStatus(sessionId: String, status: String, error: String = "") {
        update(sessionId) { current -> current.copy(status = status, error = error, hostKeyPrompt = null) }
        if (error.isNotBlank()) appendOutput(sessionId, "\n[$error]\n")
    }

    private fun appendOutput(sessionId: String, content: String) {
        update(sessionId) { current ->
            val appended = current.output + content
            current.copy(output = if (appended.length > MAX_TERMINAL_OUTPUT_CHARS) appended.takeLast(MAX_TERMINAL_OUTPUT_CHARS) else appended)
        }
    }

    private fun update(sessionId: String, transform: (AndroidTerminalSession) -> AndroidTerminalSession) {
        synchronized(lock) {
            val current = mutableSessions.value[sessionId]
            if (controls.containsKey(sessionId)) {
                val base = current ?: AndroidTerminalSession(sessionId, "", "", "", 22, "")
                mutableSessions.value = mutableSessions.value + (sessionId to transform(base))
            }
        }
    }

    private fun control(sessionId: String): SessionControl =
        controlOrNull(sessionId) ?: throw IllegalArgumentException("终端会话已关闭")

    private fun controlOrNull(sessionId: String): SessionControl? = synchronized(lock) { controls[sessionId] }

    private class SessionControl(
        val id: String,
        val connection: AndroidServerConnection,
    ) {
        @Volatile var closed = false
        @Volatile var hostKeyApproved = false
        val hostKeyDecision = CountDownLatch(1)
        var session: Session? = null
        var channel: ChannelShell? = null
    }

    private class HostKeyUserInfo(
        private val control: SessionControl,
        private val trustedHostKey: AndroidTrustedHostKey?,
        private val session: Session,
        private val onPrompt: (SessionControl, AndroidHostKeyPrompt) -> Unit,
        private val onChanged: (SessionControl) -> Unit,
    ) : UserInfo {
        override fun getPassphrase(): String? = null
        override fun getPassword(): String? = null
        override fun promptPassword(message: String?): Boolean = false
        override fun promptPassphrase(message: String?): Boolean = false
        override fun showMessage(message: String?) = Unit

        override fun promptYesNo(message: String?): Boolean {
            if (trustedHostKey != null) {
                onChanged(control)
                return false
            }
            val hostKey = session.hostKey ?: return false
            val prompt = AndroidHostKeyPrompt(
                algorithm = hostKey.type,
                keyData = hostKey.key,
                fingerprint = AndroidTrustedHostKey(hostKey.type, hostKey.key).fingerprint,
            )
            onPrompt(control, prompt)
            return control.hostKeyDecision.await(HOST_KEY_DECISION_TIMEOUT_SECONDS, TimeUnit.SECONDS) &&
                control.hostKeyApproved && !control.closed
        }
    }
}
