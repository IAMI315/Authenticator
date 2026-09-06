"""验证 RFC HOTP/TOTP 向量及不同 OTP 类型的倒计时语义。"""

from domain.otp import generate_code, remaining_seconds


def test_totp_and_hotp_vectors():
    """RFC 已知向量应保持稳定，HOTP 剩余时间语义为无过期。"""

    secret = b"12345678901234567890"
    assert generate_code(secret, "totp", 0, 30, 8, "SHA1", now=59) == "94287082"
    assert generate_code(secret, "hotp", 0, 30, 6, "SHA1", now=0) == "755224"
    assert remaining_seconds("totp", 30, now=59) == 1
    assert remaining_seconds("hotp", 30, now=59) is None
