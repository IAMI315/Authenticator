"""扫码导入的应用服务，供桌面 UI 与本机 API 共用。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from application.import_export import QrImportPayload
from application.import_service import ImportService
from domain.identifiers import normalise_group_ids


@dataclass(frozen=True)
class ScannedImportResult:
    """一次二维码导入的非敏感结果，适合直接返回给 API 调用方。"""

    source: str
    accounts_added: int
    duplicates_skipped: int
    account_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    warnings: tuple[str, ...]


class QrImportService:
    """把二维码解析结果统一交给原子 ``ImportService`` 保存。

    本类不依赖 Tkinter、截图工具或 HTTP。它只验证目标分组、为扫码所得账号
    应用分组，并保留现有导入服务的去重与保存失败回滚边界。
    """

    def __init__(self, vault: Any, import_service: ImportService) -> None:
        self.vault = vault
        self.import_service = import_service

    def normalise_group_ids(self, requested: Any) -> list[str]:
        """规范化并验证 API 指定的目标分组。"""

        group_ids = normalise_group_ids(requested)
        known = {group.id for group in self.vault.groups}
        unknown = [group_id for group_id in group_ids if group_id not in known]
        if unknown:
            raise ValueError(f"未知分组：{', '.join(unknown)}")
        return group_ids

    def import_payload(self, payload: QrImportPayload, requested_group_ids: Any = ()) -> ScannedImportResult:
        """将单条 OTP 或 Google 批量二维码事务化导入保险库。"""

        group_ids = self.normalise_group_ids(requested_group_ids)
        entries = deepcopy(payload.bundle.otp_entries)
        for entry in entries:
            entry.group_ids = normalise_group_ids([*entry.group_ids, *group_ids])

        before_ids = {entry.id for entry in self.vault.entries}
        bundle = replace(
            payload.bundle,
            otp_entries=entries,
            # QR 导入只处理 OTP 项；其余集合不应由扫描流程意外写入。
            otp_groups=[],
            password_entries=[],
            password_groups=[],
            server_profiles=[],
        )
        result = self.import_service.import_bundle(bundle)
        account_ids = tuple(entry.id for entry in self.vault.entries if entry.id not in before_ids)
        return ScannedImportResult(
            source=payload.source,
            accounts_added=result.accounts_added,
            duplicates_skipped=result.duplicates_skipped,
            account_ids=account_ids,
            group_ids=tuple(group_ids),
            warnings=tuple(bundle.warnings),
        )
