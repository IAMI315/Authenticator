package com.authenticatordesktop.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ModelsTest {
    @Test
    fun parsesStructuredSnapshotWithoutPasswordMaterial() {
        val snapshot = parseSnapshot(
            """{
                "locked": false,
                "accounts": [{
                    "id": "otp-1", "issuer": "OpenAI", "account": "alice@example.com",
                    "code": "123456", "otp_type": "totp", "type_label": "TOTP",
                    "remaining": 19, "period": 30, "favorite": true, "pinned": true, "group_ids": ["default"]
                }],
                "groups": [{"id": "default", "name": "默认分组"}],
                "account_providers": [{"key": "openai", "label": "OpenAI", "count": 1}],
                "other_provider_count": 2,
                "passwords": [{
                    "id": "pw-1", "title": "GitHub", "name": "GitHub", "username": "alice",
                    "url": "https://github.com", "notes": "", "favorite": true, "pinned": false,
                    "group_ids": ["password-default"]
                }],
                "password_groups": [{"id": "password-default", "name": "默认分组"}]
                ,"servers": [{
                    "id": "server-1", "name": "Production", "host": "203.0.113.8",
                    "port": 22, "username": "deploy", "auth_kind": "private_key",
                    "credentials_configured": true, "notes": "Primary node",
                    "trusted_fingerprint": "SHA256:abc", "trusted_algorithm": "ssh-ed25519"
                }]
            }""".trimIndent(),
        )
        assertFalse(snapshot.locked)
        assertEquals("123456", snapshot.accounts.single().code)
        assertEquals(true, snapshot.accounts.single().favorite)
        assertEquals("alice", snapshot.passwords.single().username)
        assertEquals(true, snapshot.passwords.single().favorite)
        assertEquals("默认分组", snapshot.groups.single().name)
        assertEquals("OpenAI", snapshot.accountProviders.single().label)
        assertEquals(2, snapshot.otherProviderCount)
        assertEquals("Production", snapshot.servers.single().name)
        assertEquals("SSH-ed25519".lowercase(), snapshot.servers.single().trustedAlgorithm)
    }

    @Test
    fun sortPreferencesValidateStoredValuesAndUseReadableSummaries() {
        assertEquals(AccountSortField.CREATED, AccountSortField.fromValue("unknown"))
        assertEquals(PasswordSortField.URL, PasswordSortField.fromValue("url"))
        assertEquals(MobileSortDirection.DESCENDING, MobileSortDirection.fromValue("sideways"))
        assertEquals("创建时间 · 最新优先", AccountSortPreference().summary)
        assertEquals(
            "用户名 · 升序",
            PasswordSortPreference(
                PasswordSortField.USERNAME,
                MobileSortDirection.ASCENDING,
            ).summary,
        )
    }

    @Test
    fun updatesOnlyDynamicOtpFields() {
        val snapshot = parseSnapshot(
            """{
                "locked": false,
                "accounts": [{
                    "id": "otp-1", "issuer": "OpenAI", "account": "alice@example.com",
                    "code": "123456", "otp_type": "totp", "type_label": "TOTP",
                    "remaining": 19, "period": 30, "group_ids": ["default"]
                }]
            }""".trimIndent(),
        )
        val (locked, values) = parseOtpDynamicValues(
            """{"locked":false,"values":[{"id":"otp-1","code":"654321","remaining":18,"error":""}]}""",
        )

        assertFalse(locked)
        assertEquals("654321", snapshot.withOtpDynamicValues(values).accounts.single().code)
        assertEquals(18, snapshot.withOtpDynamicValues(values).accounts.single().remaining)
    }
}
