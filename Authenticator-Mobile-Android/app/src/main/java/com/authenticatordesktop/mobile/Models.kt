package com.authenticatordesktop.mobile

import org.json.JSONArray
import org.json.JSONObject

enum class MobileSortDirection(val value: String, val label: String) {
    ASCENDING("ascending", "升序"),
    DESCENDING("descending", "降序");

    companion object {
        fun fromValue(value: String?): MobileSortDirection =
            entries.firstOrNull { it.value == value } ?: DESCENDING
    }
}

enum class AccountSortField(val value: String, val label: String) {
    CREATED("created", "创建时间"),
    SERVICE("service", "服务商"),
    ACCOUNT("account", "账号"),
    TYPE("type", "验证码类型");

    companion object {
        fun fromValue(value: String?): AccountSortField =
            entries.firstOrNull { it.value == value } ?: CREATED
    }
}

enum class PasswordSortField(val value: String, val label: String) {
    CREATED("created", "创建时间"),
    NAME("name", "名称/服务"),
    USERNAME("username", "用户名"),
    URL("url", "网址");

    companion object {
        fun fromValue(value: String?): PasswordSortField =
            entries.firstOrNull { it.value == value } ?: CREATED
    }
}

data class AccountSortPreference(
    val sortField: AccountSortField = AccountSortField.CREATED,
    val direction: MobileSortDirection = MobileSortDirection.DESCENDING,
) {
    val summary: String
        get() = "${sortField.label} · ${directionLabel(sortField == AccountSortField.CREATED)}"

    private fun directionLabel(created: Boolean): String = when (direction) {
        MobileSortDirection.ASCENDING -> if (created) "最早优先" else "升序"
        MobileSortDirection.DESCENDING -> if (created) "最新优先" else "降序"
    }
}

data class PasswordSortPreference(
    val sortField: PasswordSortField = PasswordSortField.CREATED,
    val direction: MobileSortDirection = MobileSortDirection.DESCENDING,
) {
    val summary: String
        get() = "${sortField.label} · ${directionLabel(sortField == PasswordSortField.CREATED)}"

    private fun directionLabel(created: Boolean): String = when (direction) {
        MobileSortDirection.ASCENDING -> if (created) "最早优先" else "升序"
        MobileSortDirection.DESCENDING -> if (created) "最新优先" else "降序"
    }
}

data class AccountRow(
    val id: String,
    val issuer: String,
    val account: String,
    val code: String,
    val otpType: String,
    val typeLabel: String,
    val remaining: Int?,
    val period: Int,
    val favorite: Boolean,
    val pinned: Boolean,
    val createdAt: String?,
    val groupIds: List<String>,
    val raw: JSONObject,
)

data class PasswordRow(
    val id: String,
    val title: String,
    val name: String,
    val username: String,
    val url: String,
    val notes: String,
    val favorite: Boolean,
    val pinned: Boolean,
    val createdAt: String?,
    val groupIds: List<String>,
)

data class GroupRow(val id: String, val name: String)

data class VaultSnapshot(
    val locked: Boolean = true,
    val accounts: List<AccountRow> = emptyList(),
    val groups: List<GroupRow> = emptyList(),
    val passwords: List<PasswordRow> = emptyList(),
    val passwordGroups: List<GroupRow> = emptyList(),
)

fun JSONArray.strings(): List<String> = buildList {
    repeat(length()) { add(optString(it)) }
}

fun parseSnapshot(raw: String): VaultSnapshot {
    val root = JSONObject(raw)
    fun groups(name: String): List<GroupRow> = root.optJSONArray(name)?.let { array ->
        buildList {
            repeat(array.length()) {
                val item = array.getJSONObject(it)
                add(GroupRow(item.getString("id"), item.getString("name")))
            }
        }
    } ?: emptyList()
    val accounts = root.optJSONArray("accounts")?.let { array ->
        buildList {
            repeat(array.length()) {
                val item = array.getJSONObject(it)
                add(
                    AccountRow(
                        id = item.getString("id"),
                        issuer = item.optString("issuer"),
                        account = item.optString("account"),
                        code = item.optString("code", "------"),
                        otpType = item.optString("otp_type", "totp"),
                        typeLabel = item.optString("type_label"),
                        remaining = if (item.isNull("remaining")) null else item.optInt("remaining"),
                        period = item.optInt("period", 30),
                        favorite = item.optBoolean("favorite"),
                        pinned = item.optBoolean("pinned"),
                        createdAt = item.optString("created_at").ifBlank { null },
                        groupIds = item.optJSONArray("group_ids")?.strings() ?: emptyList(),
                        raw = item,
                    ),
                )
            }
        }
    } ?: emptyList()
    val passwords = root.optJSONArray("passwords")?.let { array ->
        buildList {
            repeat(array.length()) {
                val item = array.getJSONObject(it)
                add(
                    PasswordRow(
                        id = item.getString("id"),
                        title = item.optString("title"),
                        name = item.optString("name"),
                        username = item.optString("username"),
                        url = item.optString("url"),
                        notes = item.optString("notes"),
                        favorite = item.optBoolean("favorite"),
                        pinned = item.optBoolean("pinned"),
                        createdAt = item.optString("created_at").ifBlank { null },
                        groupIds = item.optJSONArray("group_ids")?.strings() ?: emptyList(),
                    ),
                )
            }
        }
    } ?: emptyList()
    return VaultSnapshot(
        locked = root.optBoolean("locked", true),
        accounts = accounts,
        groups = groups("groups"),
        passwords = passwords,
        passwordGroups = groups("password_groups"),
    )
}
