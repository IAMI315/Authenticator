"""设备密钥保护接口与 Windows DPAPI 实现。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from infrastructure.errors import VaultError

DPAPI_ENTROPY = b"AuthenticatorDesktop/device-key/v1"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(value)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(value), pointer), buffer


class WindowsDpapiKeyProtector:
    """使用当前 Windows 用户的 DPAPI 凭据保护数据密钥。"""

    def __init__(self, entropy: bytes = DPAPI_ENTROPY) -> None:
        if os.name != "nt":
            raise VaultError("当前系统不支持 Windows DPAPI")
        self._entropy = entropy

    def protect(self, value: bytes) -> bytes:
        return self._transform(value, decrypt=False)

    def unprotect(self, value: bytes) -> bytes:
        return self._transform(value, decrypt=True)

    def _transform(self, value: bytes, *, decrypt: bool) -> bytes:
        if not value:
            raise VaultError("设备密钥数据为空")
        input_blob, input_buffer = _blob(value)
        entropy_blob, entropy_buffer = _blob(self._entropy)
        output_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
        if decrypt:
            succeeded = function(
                ctypes.byref(input_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output_blob),
            )
        else:
            succeeded = function(
                ctypes.byref(input_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output_blob),
            )
        _ = input_buffer, entropy_buffer
        if not succeeded:
            raise VaultError("无法使用当前 Windows 用户凭据处理设备密钥")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)
