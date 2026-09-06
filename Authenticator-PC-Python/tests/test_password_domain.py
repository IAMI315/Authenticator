import string

import pytest

from domain.passwords import (
    MASKED_PASSWORD,
    PasswordEntry,
    PasswordGeneratorOptions,
    generate_password,
    normalise_password_url,
    password_identity,
)


def make_entry(**overrides):
    values = {"id": "pw-1", "username": "alice@example.com", "password": "secret"}
    values.update(overrides)
    return PasswordEntry(**values)


def test_password_entry_allows_blank_name_but_requires_username_and_password():
    entry = make_entry(name="")
    entry.validate()
    assert entry.title == "alice@example.com"
    assert entry.group_ids == ["password-default"]
    with pytest.raises(ValueError, match="用户名"):
        make_entry(username="").validate()
    with pytest.raises(ValueError, match="密码"):
        make_entry(password="").validate()


def test_password_url_and_identity_are_normalised():
    entry = make_entry(name=" Example ", username=" Alice ", url="example.com/login")
    entry.validate()
    assert entry.url == "https://example.com/login"
    assert password_identity(entry) == ("example", "alice", "https://example.com/login")
    assert normalise_password_url("") == ""
    with pytest.raises(ValueError):
        normalise_password_url("ftp://example.com")


def test_password_generator_uses_every_enabled_category_and_excludes_ambiguous():
    options = PasswordGeneratorOptions(length=32)
    generated = generate_password(options)
    assert len(generated) == 32
    assert any(character in string.ascii_lowercase for character in generated)
    assert any(character in string.ascii_uppercase for character in generated)
    assert any(character in string.digits for character in generated)
    assert any(character in "!@#$%^&*()-_=+[]{};:,.?" for character in generated)
    assert not set(generated) & set("Il1O0o")
    assert len(MASKED_PASSWORD) == 12


def test_password_generator_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        generate_password(PasswordGeneratorOptions(length=7))
    with pytest.raises(ValueError):
        generate_password(
            PasswordGeneratorOptions(
                lowercase=False,
                uppercase=False,
                digits=False,
                symbols=False,
            )
        )
