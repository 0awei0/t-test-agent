from __future__ import annotations

import re

from .config import SECRET_NAMES


def redact_secrets(text: str) -> str:
    redacted = text
    for name in SECRET_NAMES:
        redacted = re.sub(
            rf"({re.escape(name)}\s*[:=]\s*)([^\s\"']+)",
            r"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]{12,}", "sk-<redacted>", redacted)
    redacted = re.sub(
        r"(https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=)[A-Za-z0-9\-]+",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(r"([?&]key=)[A-Za-z0-9\-]{8,}", r"\1<redacted>", redacted)
    return redacted
