"""验证领域标识规范化：引号、空白、大小写和默认分组不变量。"""

from domain.identifiers import account_identity, normalise_group_ids, normalise_issuer_name


class Entry:
    """提供去重函数所需字段的极简账号样本。"""

    issuer = '"xAI"'
    account = " Alice@example.com "
    secret = "JBSW Y3DP- EHPK 3PXP"
    otp_type = "TOTP"


def test_normalise_issuer_name_removes_wrapping_quotes():
    """服务商导入文本中的包裹引号应被移除。"""

    assert normalise_issuer_name(' "xAI" ') == "xAI"


def test_account_identity_is_stable_for_spacing_and_case():
    """去重键必须忽略服务商/账号大小写及密钥分隔符。"""

    assert account_identity(Entry()) == ("xai", "alice@example.com", "JBSWY3DPEHPK3PXP", "totp")


def test_normalise_group_ids_keeps_default_once():
    """默认分组始终存在、只出现一次且固定排在首位。"""

    assert normalise_group_ids(["work", "default", "work", ""]) == ["default", "work"]
