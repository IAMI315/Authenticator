"""账号和分组领域实体。

本模块只处理验证码账号、分组及其序列化规则，不依赖 Tkinter、文件或 HTTP。
``OTPEntry`` 是整个程序传递的账号类型；其 ``validate`` 方法是写入前的
唯一字段校验入口。
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from domain.identifiers import clean_secret, normalise_group_ids, normalise_issuer_name
from domain.otp import STEAM_ALPHABET, generate_code, remaining_seconds
from domain.validators import (
    infer_secret_encoding,
    integer_value,
    normalise_algorithm,
    normalise_created_at,
    normalise_type,
    utc_now_iso,
)

DEFAULT_GROUP_ID = "default"
DEFAULT_GROUP_NAME = "默认分组"
MAX_GROUP_NAME_LENGTH = 60
# ``otp_type`` 的内部值到中文界面名称的稳定映射，同时限定可接受的类型集合。
TYPE_LABELS: dict[str, str] = {
    "totp": "基于时间 (TOTP)",
    "hotp": "基于计数器 (HOTP)",
    "steam": "Steam 令牌",
    "battle": "Battle.net",
}


@dataclass
class AccountGroup:
    """账号分组值对象。

    属性类型：``id`` 为稳定字符串标识，``name`` 为显示名称，``created_at`` 为
    可选 UTC ISO-8601 时间。默认分组的标识和名称由常量固定，不能由外部数据覆盖。
    """

    id: str
    name: str
    created_at: str | None = None

    def validate(self) -> None:
        """规范化并校验当前分组；无效数据以 ``ValueError`` 终止加载或写入。"""

        self.id = str(self.id or "").strip()
        if not self.id or len(self.id) > 128:
            raise ValueError("分组标识无效")
        if self.id == DEFAULT_GROUP_ID:
            self.name = DEFAULT_GROUP_NAME
        else:
            self.name = " ".join(str(self.name or "").split())
            if not self.name:
                raise ValueError("请输入分组名称")
            if len(self.name) > MAX_GROUP_NAME_LENGTH:
                raise ValueError(f"分组名称不能超过 {MAX_GROUP_NAME_LENGTH} 个字符")
        self.created_at = normalise_created_at(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        """转换为保险库 JSON 使用的字典，不在此处执行磁盘写入。"""

        return {"id": self.id, "name": self.name, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, raw_group: dict[str, Any]) -> AccountGroup:
        """从新旧 JSON 键名构造并校验分组，兼容 ``createdAt``。"""

        if not isinstance(raw_group, dict):
            raise ValueError("分组记录必须是对象")
        group = cls(
            id=str(raw_group.get("id") or ""),
            name=str(raw_group.get("name") or ""),
            created_at=raw_group.get("created_at", raw_group.get("createdAt")),
        )
        group.validate()
        return group


def default_account_group() -> AccountGroup:
    """创建新的默认分组实例，避免多个保险库共享可变对象。"""

    return AccountGroup(id=DEFAULT_GROUP_ID, name=DEFAULT_GROUP_NAME)


@dataclass
class OTPEntry:
    """一个可生成动态验证码的账号实体。

    ``id`` 是持久化和 Treeview 行标识；``issuer``/``account`` 是显示信息；
    ``secret``、``secret_encoding``、``otp_type`` 与算法字段决定验证码。``group_ids``
    始终会被规范化为以默认分组开头的 ``list[str]``。
    """

    id: str
    issuer: str
    account: str
    secret: str
    otp_type: str = "totp"
    counter: int = 0
    period: int = 30
    digits: int = 6
    algorithm: str = "SHA1"
    secret_encoding: str = "base32"
    pinned: bool = False
    created_at: str | None = None
    group_ids: list[str] = field(default_factory=lambda: [DEFAULT_GROUP_ID])
    favorite: bool = False

    @property
    def title(self) -> str:
        """返回界面和错误信息使用的服务商标题。"""

        return self.issuer.strip() or "未命名账号"

    @property
    def type_label(self) -> str:
        """返回 ``otp_type`` 对应的中文显示名称。"""

        return TYPE_LABELS.get(self.otp_type, self.otp_type.upper())

    def validate(self) -> None:
        """校验并就地规范化可持久化字段。

        调用方应在创建、编辑、导入或生成验证码前调用本方法；它会清理密钥、
        验证参数范围、固定算法名称和分组顺序，并实际解码一次密钥。
        """

        if self.otp_type not in TYPE_LABELS:
            raise ValueError("不支持的验证码类型")
        self.secret = clean_secret(self.secret)
        if not self.secret:
            raise ValueError("请输入密钥")
        if self.secret_encoding not in ("base32", "hex"):
            raise ValueError("密钥编码必须为 Base32 或十六进制")
        if self.period < 1 or self.period > 86_400:
            raise ValueError("周期必须介于 1 到 86400 秒之间")
        if self.counter < 0:
            raise ValueError("HOTP 计数器不能为负数")
        if self.digits < 4 or self.digits > 10:
            raise ValueError("验证码位数必须介于 4 到 10 位之间")
        self.algorithm = normalise_algorithm(self.algorithm)
        self.group_ids = normalise_group_ids(self.group_ids)
        self.secret_bytes()

    def secret_bytes(self) -> bytes:
        """按 ``secret_encoding`` 解码密钥为字节；非法 Base32/十六进制会抛错。"""

        value = clean_secret(self.secret)
        try:
            if self.secret_encoding == "hex":
                if len(value) % 2:
                    value = "0" + value
                return bytes.fromhex(value)
            padding = "=" * (-len(value) % 8)
            return base64.b32decode((value.upper() + padding).encode("ascii"), casefold=True)
        except (ValueError, binascii.Error, UnicodeEncodeError) as error:
            raise ValueError("密钥不是有效的 Base32 或十六进制数据") from error

    def code(self, now: float | None = None) -> str:
        """生成当前验证码；``now`` 为可选 Unix 秒时间，便于测试和倒计时刷新。"""

        self.validate()
        return generate_code(
            self.secret_bytes(), self.otp_type, self.counter, self.period,
            self.digits, self.algorithm, now, STEAM_ALPHABET,
        )

    def remaining_seconds(self, now: float | None = None) -> int | None:
        """返回 TOTP 等待秒数；HOTP 没有自然过期时间，返回 ``None``。"""

        return remaining_seconds(self.otp_type, self.period, now)

    def to_dict(self) -> dict[str, Any]:
        """返回兼容 ``authenticator-desktop/v1`` 的账号 JSON 记录。"""

        return {
            "id": self.id, "issuer": self.issuer, "account": self.account,
            "secret": self.secret, "otp_type": self.otp_type, "counter": self.counter,
            "period": self.period, "digits": self.digits, "algorithm": self.algorithm,
            "secret_encoding": self.secret_encoding, "favorite": self.favorite,
            "pinned": self.pinned,
            "created_at": self.created_at, "group_ids": self.group_ids,
        }

    @classmethod
    def from_dict(cls, raw_entry: dict[str, Any]) -> OTPEntry:
        """从保险库或导入 JSON 构造账号，并兼容旧字段名和旧类型编号。"""

        if not isinstance(raw_entry, dict):
            raise ValueError("账号记录必须是对象")
        # ``type``、``hash``、``createdAt`` 来自历史版本/浏览器扩展备份。
        raw_type = raw_entry.get("otp_type", raw_entry.get("type", "totp"))
        otp_type, implied_encoding = normalise_type(raw_type)
        secret = str(raw_entry.get("secret", ""))
        encoding = str(raw_entry.get("secret_encoding") or implied_encoding or infer_secret_encoding(secret)).lower()
        if encoding == "auto":
            encoding = infer_secret_encoding(secret)
        entry = cls(
            id=str(raw_entry.get("id") or raw_entry.get("hash") or uuid.uuid4()),
            issuer=str(raw_entry.get("issuer") or ""), account=str(raw_entry.get("account") or ""),
            secret=secret, otp_type=otp_type,
            counter=integer_value(raw_entry.get("counter"), 0, 0, 2**63 - 1),
            period=integer_value(raw_entry.get("period"), 30, 1, 86_400),
            digits=integer_value(raw_entry.get("digits"), 6, 4, 10),
            algorithm=normalise_algorithm(raw_entry.get("algorithm", "SHA1")),
            secret_encoding=encoding, pinned=bool(raw_entry.get("pinned", False)),
            created_at=normalise_created_at(raw_entry.get("created_at", raw_entry.get("createdAt"))),
            group_ids=normalise_group_ids(raw_entry.get("group_ids", raw_entry.get("groups"))),
            favorite=bool(raw_entry.get("favorite", False)),
        )
        if entry.otp_type == "battle" and "digits" not in raw_entry:
            entry.digits = 8
        entry.validate()
        return entry

    @classmethod
    def from_uri(cls, uri: str) -> OTPEntry:
        """解析单条 ``otpauth://`` URI，并生成新的 UUID 与创建时间。"""

        parsed = urlparse(uri.strip())
        if parsed.scheme.lower() != "otpauth":
            raise ValueError("内容不是有效的 otpauth:// URI")
        otp_type, implied_encoding = normalise_type(parsed.netloc)
        parameters = parse_qs(parsed.query, keep_blank_values=True)
        secret = parameters.get("secret", [""])[0]
        if not secret:
            raise ValueError("otpauth URI 缺少密钥")
        label = unquote(parsed.path.lstrip("/"))
        issuer_from_label, account = (label.split(":", 1) if ":" in label else ("", label))
        issuer = normalise_issuer_name(unquote(parameters.get("issuer", [issuer_from_label])[0]))
        entry = cls(
            id=str(uuid.uuid4()), issuer=issuer, account=account.strip(), secret=secret,
            otp_type=otp_type,
            counter=integer_value(parameters.get("counter", [0])[0], 0, 0, 2**63 - 1),
            period=integer_value(parameters.get("period", [30])[0], 30, 1, 86_400),
            digits=integer_value(parameters.get("digits", [6])[0], 6, 4, 10),
            algorithm=normalise_algorithm(parameters.get("algorithm", ["SHA1"])[0]),
            secret_encoding=implied_encoding or infer_secret_encoding(secret), created_at=utc_now_iso(),
        )
        if entry.otp_type == "battle" and "digits" not in parameters:
            entry.digits = 8
        entry.validate()
        return entry

    def to_uri(self) -> str:
        """导出标准 ``otpauth://`` URI；HOTP 写计数器，其他类型写周期。"""

        label = self.account.strip()
        if self.issuer.strip():
            label = f"{self.issuer.strip()}:{label}" if label else self.issuer.strip()
        parameters = {"secret": self.secret, "algorithm": self.algorithm, "digits": str(self.digits)}
        if self.issuer.strip():
            parameters["issuer"] = self.issuer.strip()
        if self.otp_type == "hotp":
            parameters["counter"] = str(self.counter)
        else:
            parameters["period"] = str(self.period)
        query = "&".join(f"{quote(key)}={quote(value)}" for key, value in parameters.items())
        return f"otpauth://{self.otp_type}/{quote(label)}?{query}"
