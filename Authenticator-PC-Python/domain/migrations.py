"""Pure compatibility migrations for persisted desktop documents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def migrate_legacy_star_records(document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Move legacy star/pinned state to favorite for records without the new field."""

    migrated = deepcopy(document)
    changed = False
    for collection_name in ("entries", "password_entries"):
        records = migrated.get(collection_name, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or "favorite" in record:
                continue
            record["favorite"] = bool(record.get("pinned", False))
            record["pinned"] = False
            changed = True
    return migrated, changed
