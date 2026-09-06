"""Guard the password-book dependency boundaries against accidental coupling."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_files(directory: str):
    return (path for path in (ROOT / directory).rglob("*.py") if "__pycache__" not in path.parts)


def test_domain_and_application_do_not_depend_on_tkinter_or_presentation():
    forbidden = ("import tkinter", "from tkinter", "from presentation", "import presentation")
    for directory in ("domain", "application"):
        for path in source_files(directory):
            source = path.read_text(encoding="utf-8")
            assert not any(marker in source for marker in forbidden), path


def test_password_ui_does_not_mutate_vault_collections_directly():
    mutation_markers = (
        "vault.password_entries.append",
        "vault.password_entries.extend",
        "vault.password_entries.remove",
        "vault.password_entries =",
        "vault.password_groups.append",
        "vault.password_groups.remove",
        "vault.password_groups =",
    )
    for path in source_files("presentation"):
            source = path.read_text(encoding="utf-8")
            assert not any(marker in source for marker in mutation_markers), path


def test_import_export_ui_does_not_read_or_write_files_directly():
    source = (ROOT / "presentation" / "mixins" / "import_export.py").read_text(encoding="utf-8")
    forbidden = ("from pathlib", "Path(", ".read_text(", ".write_text(", "os.replace")
    assert not any(marker in source for marker in forbidden)
