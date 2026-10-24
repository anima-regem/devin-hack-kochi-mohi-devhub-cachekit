"""Pure configured redaction; raw hole values never become report evidence."""

import re


def redact(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        text = re.sub(pattern, "<redacted>", text)
    return text
