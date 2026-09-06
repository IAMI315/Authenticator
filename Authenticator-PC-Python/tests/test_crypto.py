"""验证 AES-GCM 信封的正常解密、错误密码和篡改拒绝行为。"""

import pytest

from infrastructure.crypto import VaultCryptoError, decrypt_payload, encrypt_payload


def test_crypto_round_trip_and_wrong_password():
    """正确密码应解出原始负载，错误密码必须归一化为加密错误。"""

    payload = {"entries": [{"account": "alice@example.com"}], "groups": []}
    envelope, _key, _salt = encrypt_payload(payload, "correct", b"test-aad", 100_000)
    decoded, _decoded_key, _decoded_salt, iterations = decrypt_payload(
        envelope, "correct", b"test-aad"
    )
    assert decoded == payload
    assert iterations == 100_000

    with pytest.raises(VaultCryptoError):
        decrypt_payload(envelope, "wrong", b"test-aad")


def test_crypto_rejects_tampered_envelope():
    """认证加密应拒绝被篡改的密文，而不能返回部分负载。"""

    envelope, _key, _salt = encrypt_payload({"value": 1}, "password", b"aad", 100_000)
    envelope["cipher"]["data"] = envelope["cipher"]["data"][:-2] + "AA"
    with pytest.raises(VaultCryptoError):
        decrypt_payload(envelope, "password", b"aad")
