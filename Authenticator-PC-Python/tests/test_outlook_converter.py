"""Regression coverage for the standalone Outlook TXT converter script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from application.import_export import parse_import_text


def _converter_module():
    path = Path(__file__).parents[1] / "scripts" / "convert_outlook_txt_to_authenticator.py"
    spec = importlib.util.spec_from_file_location("outlook_converter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outlook_converter_creates_importable_password_book_without_extra_fields(tmp_path: Path) -> None:
    converter = _converter_module()
    source = tmp_path / "accounts.txt"
    source.write_text(
        "====DAY1====\n"
        "alice@outlook.com----password-one----ignored-id----ignored-token\n"
        "\n"
        "====DAY2====\n"
        "bob@outlook.com----password-two----ignored-id----ignored-token\n"
        "alice@outlook.com----new-password----ignored-id----ignored-token\n",
        encoding="utf-8",
    )

    entries, skipped = converter.parse_records(
        source,
        service_name="Outlook",
        site_url="https://outlook.live.com/",
    )
    document = converter.build_backup(entries)
    bundle = parse_import_text(converter.json.dumps(document, ensure_ascii=False))

    assert len(entries) == 2
    assert skipped == [6]
    assert [entry.username for entry in bundle.password_entries] == ["alice@outlook.com", "bob@outlook.com"]
    assert [entry.password for entry in bundle.password_entries] == ["password-one", "password-two"]
    assert all(entry.name == "Outlook" for entry in bundle.password_entries)
    assert all(entry.notes == "" for entry in bundle.password_entries)
    assert "ignored-token" not in converter.json.dumps(document, ensure_ascii=False)
