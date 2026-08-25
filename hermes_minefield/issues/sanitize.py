"""Sanitize issue/candidate packets before any preview or upload."""

from __future__ import annotations

from typing import Any, Mapping

from ..privacy import redact_text, sanitize_mapping, strip_url_credentials


FORBIDDEN_KEYS = {
    "authorization",
    "api_key",
    "token",
    "password",
    "cookie",
    "private_key",
    "ssh",
    "prompt",
    "messages",
    "conversation",
    "tool_output",
}


def sanitize_issue_body(text: str) -> str:
    return redact_text(text, keep_ips=False)


def sanitize_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    # Strip URL credentials before general redaction — otherwise IP redaction
    # can turn userinfo@host into a form urlsplit no longer parses cleanly.
    pre: dict[str, Any] = dict(packet)
    env = pre.get("environment")
    if isinstance(env, Mapping):
        env2 = dict(env)
        url = env2.get("base_url")
        if isinstance(url, str):
            env2["base_url"] = strip_url_credentials(url)
        pre["environment"] = env2
    cleaned = sanitize_mapping(pre, drop_keys=FORBIDDEN_KEYS)
    if isinstance(cleaned.get("environment"), dict):
        url2 = cleaned["environment"].get("base_url")
        if isinstance(url2, str):
            cleaned["environment"]["base_url"] = redact_text(url2)
    return cleaned
