"""领域实体与适配器共享的无副作用值规范化函数。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from domain.identifiers import clean_secret

# 支持的 HMAC 摘要算法；实体和 UI 下拉选项都以该元组为准。
ALGORITHMS: tuple[str, ...] = ("SHA1", "SHA256", "SHA512")


def infer_secret_encoding(secret: str) -> str:
    """依据字符集推断 Base32 或十六进制；无法确定时保守地按 Base32 处理。"""

    value = clean_secret(secret)
    if re.fullmatch(r"[A-Z2-7]+=*", value.upper()):
        return "base32"
    if re.fullmatch(r"[0-9A-F]+", value.upper()):
        return "hex"
    return "base32"


def normalise_type(value: Any) -> tuple[str, str | None]:
    """兼容历史数字/别名类型，返回内部类型及其隐含密钥编码。"""

    if isinstance(value, int):
        numeric_types = {1: "totp", 2: "hotp", 3: "battle", 4: "steam", 5: "totp", 6: "hotp"}
        if value not in numeric_types:
            raise ValueError("不支持的验证码类型")
        return numeric_types[value], "hex" if value in (5, 6) else None
    raw_type = str(value or "totp").strip().lower()
    aliases = {
        "totp": "totp", "hotp": "hotp", "steam": "steam", "battle": "battle",
        "battlenet": "battle", "battle.net": "battle", "hex": "totp", "hhex": "hotp",
    }
    if raw_type not in aliases:
        raise ValueError("不支持的验证码类型")
    return aliases[raw_type], "hex" if raw_type in ("hex", "hhex") else None


def normalise_algorithm(value: Any) -> str:
    """将历史数字或带连字符的算法名转为 ``SHA1/SHA256/SHA512``。"""

    if isinstance(value, int):
        value = {1: "SHA1", 2: "SHA256", 3: "SHA512"}.get(value, "SHA1")
    algorithm = str(value or "SHA1").upper().replace("-", "")
    if algorithm not in ALGORITHMS:
        raise ValueError("仅支持 SHA-1、SHA-256 和 SHA-512 算法")
    return algorithm


def integer_value(value: Any, default: int, minimum: int, maximum: int) -> int:
    """安全转换整数并限制闭区间；不可转换时返回调用方提供的默认值。"""

    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def utc_now_iso() -> str:
    """返回毫秒精度的 UTC ISO-8601 创建时间字符串。"""

    return datetime.now(UTC).isoformat(timespec="milliseconds")


def normalise_created_at(value: Any) -> str | None:
    """兼容时间戳和 ISO 字符串；非法或缺失时间返回 ``None``。"""

    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(float(value), UTC)
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat(timespec="milliseconds")
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def created_at_timestamp(value: str | None) -> float:
    """将可选创建时间转成排序时间戳；历史数据固定排在较旧的位置。"""

    normalised = normalise_created_at(value)
    if not normalised:
        return float("-inf")
    return datetime.fromisoformat(normalised).timestamp()


def format_created_at(value: str | None) -> str:
    """生成列表显示的本地时间文本；无有效时间时显示“历史数据”。"""

    normalised = normalise_created_at(value)
    if not normalised:
        return "历史数据"
    return datetime.fromisoformat(normalised).astimezone().strftime("%Y-%m-%d %H:%M")
