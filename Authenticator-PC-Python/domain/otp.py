"""TOTP、HOTP、Steam 和 Battle.net 使用的纯验证码计算函数。"""

from __future__ import annotations

import hmac
import time

# Steam Guard 的 26 字符字母表；Steam 类型固定输出 5 个字符。
STEAM_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"


def generate_code(
    secret_bytes: bytes,
    otp_type: str,
    counter: int,
    period: int,
    digits: int,
    algorithm: str,
    now: float | None = None,
    steam_alphabet: str = STEAM_ALPHABET,
) -> str:
    """根据密钥和 OTP 参数生成验证码。

    ``counter`` 仅供 HOTP 使用；其他类型通过 ``now // period`` 计算时间计数器。
    返回值始终为字符串，Steam 使用字母表，其余类型为补零后的数字。
    """

    if now is None:
        now = time.time()
    # HOTP 是显式计数器；TOTP/Steam/Battle.net 使用时间步长派生计数器。
    current_counter = counter if otp_type == "hotp" else int(now) // period
    message = current_counter.to_bytes(8, "big")
    digest = hmac.new(secret_bytes, message, algorithm.lower()).digest()
    offset = digest[-1] & 0x0F
    number = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    if otp_type == "steam":
        code = ""
        for _ in range(5):
            code += steam_alphabet[number % len(steam_alphabet)]
            number //= len(steam_alphabet)
        return code
    return str(number % (10**digits)).zfill(digits)


def remaining_seconds(otp_type: str, period: int, now: float | None = None) -> int | None:
    """计算下一个时间片前的剩余秒数；HOTP 不会随时间失效。"""

    if otp_type == "hotp":
        return None
    if now is None:
        now = time.time()
    return period - (int(now) % period)
