"""可复用 Tkinter 对话框的集中导出。"""

from presentation.dialogs.entry import EntryDialog
from presentation.dialogs.google_export import GoogleAuthenticatorExportDialog
from presentation.dialogs.groups import GroupAssignmentDialog, GroupManagerDialog, GroupNameDialog
from presentation.dialogs.password import MasterPasswordChangeDialog, PasswordDialog
from presentation.dialogs.password_entry import PasswordDialog as PasswordEntryDialog
from presentation.dialogs.qr_region import ScreenRegionSelector
from presentation.dialogs.settings import SettingsDialog
from presentation.dialogs.text_import import TextImportDialog

__all__ = [
    "EntryDialog",
    "GoogleAuthenticatorExportDialog",
    "GroupAssignmentDialog",
    "GroupManagerDialog",
    "GroupNameDialog",
    "PasswordDialog",
    "MasterPasswordChangeDialog",
    "PasswordEntryDialog",
    "ScreenRegionSelector",
    "SettingsDialog",
    "TextImportDialog",
]
