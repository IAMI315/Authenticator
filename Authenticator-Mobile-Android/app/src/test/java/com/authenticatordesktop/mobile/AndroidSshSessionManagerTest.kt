package com.authenticatordesktop.mobile

import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidSshSessionManagerTest {
    @Test
    fun hostKeyRepositoryAcceptsJschDefaultNullLookup() {
        val repository = ProfileHostKeyRepository(null)

        assertTrue(repository.getHostKey(null, null).isEmpty())
    }

    @Test
    fun dismissRemovesTerminalTabImmediately() {
        val manager = AndroidSshSessionManager()
        val sessionId = manager.connect(
            AndroidServerConnection(
                id = "server-1",
                name = "Test server",
                host = "127.0.0.1",
                port = 1,
                username = "tester",
                authKind = "password",
                password = "password",
                privateKey = "",
                privateKeyPassphrase = "",
                trustedHostKey = null,
            ),
        )

        manager.dismiss(sessionId)

        assertTrue(sessionId !in manager.sessions.value)
    }
}
