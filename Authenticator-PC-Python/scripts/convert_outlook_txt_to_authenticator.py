"""Convert Outlook account lines to an Authenticator password-book JSON backup.

Input records use this format, with optional DAY separator lines::

    email@outlook.com----password----extra-id----token

Only the first two fields are imported. Extra identifiers and tokens are deliberately
discarded, so this script does not copy them to an Authenticator password record.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

FORMAT = "authenticator-desktop/v1"
PASSWORD_DEFAULT_GROUP_ID = "password-default"
OUTLOOK_URL = "https://outlook.live.com/"


def utc_now_iso() -> str:
    """Return an RFC 3339 UTC timestamp accepted by Authenticator imports."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_separator(line: str) -> bool:
    """Return true for section lines such as ``====DAY1====``."""

    stripped = line.strip()
    return len(stripped) >= 6 and stripped.startswith("===") and stripped.endswith("===")


def looks_like_email(value: str) -> bool:
    """Perform a deliberately small sanity check without rejecting valid local parts."""

    local, separator, domain = value.partition("@")
    return bool(separator and local and domain and "." in domain and not any(char.isspace() for char in value))


def parse_records(source: Path, *, service_name: str, site_url: str) -> tuple[list[dict[str, object]], list[int]]:
    """Parse non-empty account records, returning entries and skipped line numbers."""

    created_at = utc_now_iso()
    entries: list[dict[str, object]] = []
    skipped_lines: list[int] = []
    seen_usernames: set[str] = set()

    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), start=1):
        # Do not strip the full record: trailing whitespace may be part of a password.
        line = raw_line.rstrip("\r\n")
        if not line.strip() or is_separator(line):
            continue
        fields = line.split("----", maxsplit=3)
        if len(fields) < 2:
            skipped_lines.append(line_number)
            continue
        username, password = fields[0].strip(), fields[1]
        if not username or not password or not looks_like_email(username):
            skipped_lines.append(line_number)
            continue
        normalized_username = username.casefold()
        if normalized_username in seen_usernames:
            skipped_lines.append(line_number)
            continue
        seen_usernames.add(normalized_username)
        entries.append(
            {
                "id": str(uuid.uuid4()),
                "name": service_name,
                "username": username,
                "password": password,
                "url": site_url,
                "notes": "",
                "favorite": False,
                "pinned": False,
                "created_at": created_at,
                "group_ids": [PASSWORD_DEFAULT_GROUP_ID],
            }
        )
    return entries, skipped_lines


def build_backup(entries: list[dict[str, object]]) -> dict[str, object]:
    """Build the documented plain Authenticator desktop import payload."""

    exported_at = utc_now_iso()
    return {
        "format": FORMAT,
        "version": 1,
        "exported_at": exported_at,
        "encrypted": False,
        "entries": [],
        "groups": [],
        "password_entries": entries,
        "password_groups": [
            {
                "id": PASSWORD_DEFAULT_GROUP_ID,
                "name": "默认分组",
                "created_at": exported_at,
            }
        ],
        "server_profiles": [],
    }


def normalise_site_url(value: str) -> str:
    """Validate the optional site URL using the same HTTP(S)-only policy as the app."""

    url = value.strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--url 必须是有效的 HTTP 或 HTTPS 地址")
    return url


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 Outlook 邮箱----密码----附加字段 TXT 转为验证器密码本明文 JSON。"
    )
    parser.add_argument("input", type=Path, help="待转换的 UTF-8 TXT 文件")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出 JSON 路径；省略时写入输入文件同目录的 *-authenticator-passwords.json",
    )
    parser.add_argument("--service-name", default="Outlook", help="密码本中的名称/服务，默认 Outlook")
    parser.add_argument("--url", default=OUTLOOK_URL, help=f"密码本中的网址，默认 {OUTLOOK_URL}")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    source = args.input.expanduser().resolve()
    if not source.is_file():
        print(f"错误：找不到输入文件：{source}", file=sys.stderr)
        return 2
    if not args.service_name.strip():
        print("错误：--service-name 不能为空", file=sys.stderr)
        return 2
    output = args.output.expanduser().resolve() if args.output else source.with_name(
        f"{source.stem}-authenticator-passwords.json"
    )
    if output == source:
        print("错误：输出文件不能覆盖输入 TXT", file=sys.stderr)
        return 2

    try:
        site_url = normalise_site_url(args.url)
        entries, skipped_lines = parse_records(
            source,
            service_name=args.service_name.strip(),
            site_url=site_url,
        )
    except UnicodeDecodeError:
        print("错误：输入文件必须是 UTF-8 或 UTF-8 with BOM 编码", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    if not entries:
        print("错误：没有找到可转换的邮箱----密码记录", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_backup(entries), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已输出 {len(entries)} 条密码记录：{output}")
    if skipped_lines:
        preview = ", ".join(map(str, skipped_lines[:20]))
        suffix = " ..." if len(skipped_lines) > 20 else ""
        print(f"已跳过 {len(skipped_lines)} 行（空行、标题、格式无效或重复邮箱）：{preview}{suffix}")
    print("输出为明文 JSON，导入后请妥善保存或删除该文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
