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
                "passwords": [{
                    "id": "pw-1", "title": "GitHub", "name": "GitHub", "username": "alice",
                    "url": "https://github.com", "notes": "", "favorite": true, "pinned": false,
                    "group_ids": ["password-default"]
                }],
                "password_groups": [{"id": "password-default", "name": "默认分组"}]
            }""".trimIndent(),
        )
        assertFalse(snapshot.locked)
        assertEquals("123456", snapshot.accounts.single().code)
        assertEquals(true, snapshot.accounts.single().favorite)
        assertEquals("alice", snapshot.passwords.single().username)
        assertEquals(true, snapshot.passwords.single().favorite)
        assertEquals("默认分组", snapshot.groups.single().name)
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
}
