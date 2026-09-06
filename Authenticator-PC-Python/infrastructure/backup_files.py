"""备份文件的 UTF-8 读取与原子 JSON 写入适配器。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class JsonBackupFileStore:
    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8-sig")

    def write_document(self, path: str, document: dict[str, Any]) -> None:
        self.write_text(path, json.dumps(document, ensure_ascii=False, indent=2))

    def write_text(self, path: str, content: str) -> None:
        target = Path(path)
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
