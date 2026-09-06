package com.authenticatordesktop.mobile

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python

class PythonGateway(context: Context) {
    private val facade: PyObject = Python.getInstance()
        .getModule("mobile_facade")
        .callAttr("create_facade", context.filesDir.absolutePath, AndroidKeyProtector(context))

    private fun call(name: String, vararg args: Any?): String =
        facade.callAttr(name, *args).toString()

    fun startup() = call("startup")
    fun initialize(password: String) = call("initialize", password)
    fun unlock(password: String) = call("unlock", password)
    fun lock() = call("lock")
    fun changeMasterPassword(current: String, next: String) = call("change_master_password", current, next)
    fun snapshot(
        accountQuery: String,
        passwordQuery: String,
        accountGroup: String,
        passwordGroup: String,
        accountFavoriteOnly: Boolean,
        passwordFavoriteOnly: Boolean,
        accountShowPinned: Boolean,
        passwordShowPinned: Boolean,
        accountSort: AccountSortPreference,
        passwordSort: PasswordSortPreference,
    ) = call(
        "snapshot",
        accountQuery,
        passwordQuery,
        accountGroup,
        passwordGroup,
        false,
        accountSort.sortField.value,
        accountSort.direction.value,
        passwordSort.sortField.value,
        passwordSort.direction.value,
        accountFavoriteOnly,
        passwordFavoriteOnly,
        accountShowPinned,
        passwordShowPinned,
    )
    fun processQrPayload(uri: String) = call("process_qr_payload", uri)
    fun createAccount(json: String) = call("create_account", json)
    fun updateAccount(json: String) = call("update_account", json)
    fun deleteAccounts(ids: String) = call("delete_accounts", ids)
    fun toggleAccountPinned(id: String) = call("toggle_account_pinned", id)
    fun setAccountPinned(ids: String, pinned: Boolean) = call("set_account_pinned", ids, pinned)
    fun setAccountFavorite(ids: String, favorite: Boolean) = call("set_account_favorite", ids, favorite)
    fun incrementHotp(id: String) = call("increment_hotp", id)
    fun createGroup(name: String) = call("create_group", name)
    fun renameGroup(id: String, name: String) = call("rename_group", id, name)
    fun deleteGroup(id: String) = call("delete_group", id)
    fun assignAccountGroups(ids: String, groups: String) = call("assign_account_groups", ids, groups)
    fun getPassword(id: String) = call("get_password", id)
    fun createPassword(json: String) = call("create_password", json)
    fun updatePassword(id: String, json: String) = call("update_password", id, json)
    fun deletePasswords(ids: String) = call("delete_passwords", ids)
    fun setPasswordPinned(ids: String, pinned: Boolean) = call("set_password_pinned", ids, pinned)
    fun setPasswordFavorite(ids: String, favorite: Boolean) = call("set_password_favorite", ids, favorite)
    fun createPasswordGroup(name: String) = call("create_password_group", name)
    fun renamePasswordGroup(id: String, name: String) = call("rename_password_group", id, name)
    fun deletePasswordGroup(id: String) = call("delete_password_group", id)
    fun assignPasswordGroups(ids: String, groups: String) = call("assign_password_groups", ids, groups)
    fun generatePassword(json: String) = call("generate_password", json)
    fun exportGoogleAuthenticator() = call("export_google_authenticator")
    fun exportBackup(encrypted: Boolean) = call("export_backup", encrypted)
    fun importBackup(content: String, password: String) = call("import_backup", content, password)
}
