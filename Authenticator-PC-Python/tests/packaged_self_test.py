"""可嵌入打包 EXE 的轻量自检，不依赖 Tk 窗口或外部用户数据。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from application.import_export import parse_qr_content
from domain.entities import OTPEntry
from domain.passwords import PasswordEntry, PasswordGeneratorOptions, generate_password
from infrastructure.api_router import ApiRoute, ApiRouter
from infrastructure.qr_scanner import QrScanner
from infrastructure.secure_storage import StorageLoadKind
from infrastructure.settings_store import SettingsStore
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault


def run_self_test() -> None:
    """验证 OTP 向量、URI、扫码依赖、加密保险库、设置和 API 路由关键契约。"""

    # 这些 RFC 向量可快速发现密码学、时间计数器或打包依赖回归。
    shared_secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    hotp = OTPEntry(
        id="test-hotp",
        issuer="Test",
        account="hotp",
        secret=shared_secret,
        otp_type="hotp",
        counter=0,
    )
    assert hotp.code() == "755224", "RFC 4226 HOTP vector failed"
    totp = OTPEntry(id="test-totp", issuer="Test", account="totp", secret=shared_secret, digits=8)
    assert totp.code(now=59) == "94287082", "RFC 6238 TOTP vector failed"

    imported = OTPEntry.from_uri(
        "otpauth://totp/%22xAI%22:alice?secret=JBSWY3DPEHPK3PXP&issuer=%22xAI%22"
    )
    assert imported.issuer == "xAI" and imported.account == "alice"

    import zxingcpp

    qr_image = zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, imported.to_uri(), 320, 320)
    decoded = QrScanner(parse_qr_content).decode(qr_image)
    scanned_entry = decoded.bundle.otp_entries[0]
    assert scanned_entry.issuer == "xAI" and scanned_entry.account == "alice"

    generated = generate_password(PasswordGeneratorOptions(length=24))
    assert len(generated) == 24, "Password generator length failed"

    # 所有文件测试在临时目录完成，不能触碰 EXE 同级的正式便携式数据。
    with tempfile.TemporaryDirectory(prefix="authenticator-self-test-") as directory:
        root = Path(directory)
        repository = JsonVaultRepository(root / "vault.json", Vault)
        vault = repository.create()
        vault.entries.append(imported)
        vault.password_entries.append(
            PasswordEntry(id="test-password", username="alice", password=generated, name="Example")
        )
        vault.secure_settings = {"api_token": "packaged-self-test-token-value-123456789"}
        repository.initialize(vault, "test-password")
        loaded = repository.create()
        assert repository.load(loaded).kind == StorageLoadKind.AUTO_UNLOCKED
        assert loaded.entries[0].secret == imported.secret
        assert loaded.password_entries[0].password == generated
        repository.lock(loaded)
        assert loaded.entries == [] and loaded.password_entries == []
        repository.unlock(loaded, "test-password")
        assert loaded.entries[0].secret == imported.secret

        settings = SettingsStore(root / "settings.json")
        settings.load()
        assert len(settings.api_token) >= 32
        settings.save()
        assert settings.api_token not in (root / "settings.json").read_text(encoding="utf-8")

    assert ApiRouter().match("GET", "/v1/accounts/account-1/secret") == ApiRoute(
        "get_secret", {"id": "account-1"}
    )
    print("Authenticator Desktop self-test passed.")
