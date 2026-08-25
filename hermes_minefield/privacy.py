"""Metadata-first redaction helpers for recorder / incidents / issues."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)ghp_[a-z0-9]{20,}"),
    re.compile(r"(?i)github_pat_[a-z0-9_]{20,}"),
    re.compile(r"(?i)sk-[a-z0-9]{20,}"),
    re.compile(r"(?i)ssh-rsa\s+[a-z0-9+/=]+"),
    # Future bank-tool plaintext shapes (groundwork; bank access not enabled)
    re.compile(r"(?i)\b(pin|mfa|otp|sms[_-]?code|cvv|security[_-]?answer)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(bsb|account[_-]?number|card[_-]?number)\s*[:=]\s*([0-9\-\s]{4,})"),
]
_ABS_HOME = re.compile(r"(?i)(/home/|/Users/|C:\\Users\\)[^\s\"']+")
_IP_LIKE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)


def stable_hash(value: Any, *, n: int = 12) -> str:
    raw = value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:n]


def arg_fingerprint(args: Any) -> str:
    """Privacy-safe fingerprint of tool arguments (no raw content persisted)."""
    try:
        import json

        blob = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        blob = repr(args)
    return stable_hash(blob, n=16)


def strip_url_credentials(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.username or parts.password:
            netloc = parts.hostname or ""
            if parts.port:
                netloc = f"{netloc}:{parts.port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    return url


def redact_text(text: str, *, keep_ips: bool = False) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    out = _ABS_HOME.sub("[REDACTED_PATH]", out)
    if not keep_ips:
        out = _IP_LIKE.sub("[REDACTED_IP]", out)
    return out


def sanitize_mapping(data: Mapping[str, Any], *, drop_keys: Optional[set[str]] = None) -> dict[str, Any]:
    drop = {k.lower() for k in (drop_keys or set())} | {
        "authorization",
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "cookie",
        "set-cookie",
        "access_token",
        "refresh_token",
        # Future bank-tool fields (groundwork; bank access not enabled yet)
        "pin",
        "mfa",
        "mfa_code",
        "otp",
        "one_time_password",
        "sms_code",
        "security_answer",
        "recovery_code",
        "bsb",
        "account_number",
        "card_number",
        "cvv",
        "iban",
    }
    out: dict[str, Any] = {}
    for k, v in data.items():
        if str(k).lower() in drop:
            out[k] = "[REDACTED]"
            continue
        if isinstance(v, Mapping):
            out[k] = sanitize_mapping(v, drop_keys=drop_keys)
        elif isinstance(v, str):
            out[k] = redact_text(v)
        elif isinstance(v, list):
            out[k] = [
                sanitize_mapping(x, drop_keys=drop_keys)
                if isinstance(x, Mapping)
                else (redact_text(x) if isinstance(x, str) else x)
                for x in v
            ]
        else:
            out[k] = v
    return out


def looks_like_approval(text: str) -> bool:
    """True only for explicit human approval phrases — model chatter never counts."""
    t = (text or "").strip().lower()
    return t in {"y", "yes", "approve", "submit", "confirm"}
