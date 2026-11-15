"""Deterministic synthetic-data redaction; never discovers host credentials."""

import re
from collections import Counter
from dataclasses import dataclass

from pydantic import JsonValue

KEYS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "set-cookie",
    "approval_token",
)
ASSIGNMENT = re.compile(r"(?i)(?<![\w])(?:" + "|".join(KEYS) + r")[\"']?\s*[:=]")
PEM = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----",
    re.DOTALL,
)
AUTH = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[^\s,;\"']+")


class RedactionError(ValueError):
    """Input cannot be safely represented without ambiguous data loss."""


@dataclass(frozen=True)
class RedactionResult:
    value: JsonValue
    counts: tuple[tuple[str, int], ...]

    @property
    def rules(self) -> tuple[str, ...]:
        return tuple(rule for rule, _ in self.counts)


def _marker(value: str) -> str:
    return "REDACTED" + "".join(re.findall(r"\r\n|\r|\n", value))


class Redactor:
    def __init__(self, literals: tuple[str, ...] = ()) -> None:
        if any(not isinstance(value, str) or not value for value in literals):
            raise RedactionError("literal values must be nonempty strings")
        self._literals = (
            re.compile(
                "|".join(re.escape(v) for v in sorted(set(literals), key=lambda x: (-len(x), x)))
            )
            if literals
            else None
        )

    def sanitize(self, value: JsonValue) -> RedactionResult:
        counts: Counter[str] = Counter()

        def substitute(pattern: re.Pattern[str], text: str, rule: str) -> str:
            def replace(match: re.Match[str]) -> str:
                counts[rule] += 1
                return _marker(match.group())

            return pattern.sub(replace, text)

        def clean_text(text: str) -> str:
            # Remove whole credential lines before literal substitution can obscure their keys.
            text = substitute(PEM, text, "private_key")
            lines = text.splitlines(keepends=True)
            text = "".join(redact_line(line) if ASSIGNMENT.search(line) else line for line in lines)
            text = substitute(AUTH, text, "authorization")
            if self._literals is not None:
                text = substitute(self._literals, text, "literal")
            return text

        def redact_line(line: str) -> str:
            counts["credential_assignment"] += 1
            return _marker(line)

        def walk(item: JsonValue, depth: int = 0) -> JsonValue:
            if depth > 64:
                raise RedactionError("redaction nesting limit exceeded")
            if isinstance(item, str):
                return clean_text(item)
            if isinstance(item, list):
                return [walk(entry, depth + 1) for entry in item]
            if isinstance(item, dict):
                result: dict[str, JsonValue] = {}
                for key, entry in item.items():
                    safe_key = clean_text(key)
                    if safe_key in result:
                        raise RedactionError("redacted JSON keys collide")
                    if key.casefold() in KEYS and entry is not None:
                        counts["sensitive_key"] += 1
                        result[safe_key] = "REDACTED"
                    else:
                        result[safe_key] = walk(entry, depth + 1)
                return result
            return item

        sanitized = walk(value)
        return RedactionResult(sanitized, tuple(sorted(counts.items())))
