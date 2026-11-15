"""Synthetic secrets only; redaction is not a production detection guarantee."""

import pytest
from pydantic import JsonValue

from agentforge.core.redaction import KEYS, RedactionError, Redactor


@pytest.mark.parametrize("key", KEYS)
def test_nested_sensitive_keys_and_assignments(key: str) -> None:
    result = Redactor().sanitize({"nested": [{key.upper(): "synthetic-value"}]})
    assert result.value == {"nested": [{key.upper(): "REDACTED"}]}
    assert result.counts == (("sensitive_key", 1),)
    text = f"ok\r\nprefix {key}=synthetic value with spaces\r\nlast"
    assert Redactor().sanitize(text).value == "ok\r\nREDACTED\r\nlast"


def test_pem_headers_literals_unicode_and_line_numbers() -> None:
    text = (
        "α synthetic-long synthetic\nBearer abc123\nBasic Zm9v\n"
        "-----BEGIN RSA PRIVATE KEY-----\nsynthetic-key-data\n"
        "-----END RSA PRIVATE KEY-----\ntail\n"
    )
    result = Redactor(("synthetic", "synthetic-long")).sanitize(text)
    assert isinstance(result.value, str)
    assert result.value.count("\n") == text.count("\n")
    for secret in ("synthetic", "abc123", "Zm9v", "PRIVATE KEY"):
        assert secret not in result.value
    assert result.value.startswith("α REDACTED REDACTED\n")
    assert result.rules == ("authorization", "literal", "private_key")


def test_invalid_literals_collision_and_depth_fail_closed() -> None:
    with pytest.raises(RedactionError):
        Redactor(("",))
    with pytest.raises(RedactionError, match="collide"):
        Redactor(("one", "two")).sanitize({"one": 1, "two": 2})
    nested = "[" * 70 + '"leaf"' + "]" * 70
    import json

    with pytest.raises(RedactionError, match="nesting"):
        Redactor().sanitize(json.loads(nested))


def test_partial_assignment_and_input_not_mutated() -> None:
    raw: dict[str, JsonValue] = {"password": {"nested": "synthetic"}, "normal": [True, 1, None]}
    assert Redactor().sanitize(raw).value == {"password": "REDACTED", "normal": [True, 1, None]}
    assert raw["password"] == {"nested": "synthetic"}
    assert Redactor().sanitize("password=unfinished").value == "REDACTED"
