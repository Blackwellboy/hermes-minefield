"""Privacy-safe target fingerprint for Lite cache (Phase 9 lite support)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .version import PROBE_PLAN_VERSION, __version__


@dataclass(frozen=True)
class Fingerprint:
    key: str
    components: dict[str, Any]

    def short(self) -> str:
        return self.key[:12]


def _h(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_fingerprint(
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    runtime: Optional[str] = None,
    runtime_version: Optional[str] = None,
    quant: Optional[str] = None,
    chat_template_hash: Optional[str] = None,
    reasoning_mode: Optional[str] = None,
    tool_mode: Optional[str] = None,
    generation_settings: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Fingerprint:
    # Strip hostnames from base_url for privacy — keep only scheme+path shape hint
    url_shape = None
    if base_url:
        try:
            from urllib.parse import urlsplit

            parts = urlsplit(base_url)
            url_shape = f"{parts.scheme}://[host]{parts.path}"
        except Exception:
            url_shape = "[url]"

    components = {
        "model": model,
        "url_shape": url_shape,
        "runtime": runtime,
        "runtime_version": runtime_version,
        "quant": quant,
        "chat_template_hash": chat_template_hash,
        "reasoning_mode": reasoning_mode,
        "tool_mode": tool_mode,
        "generation_settings": dict(generation_settings or {}),
        "minefield_plugin": __version__,
        "probe_plan_version": PROBE_PLAN_VERSION,
    }
    if extra:
        # Only allow explicitly passed non-PII keys
        for k, v in extra.items():
            if k.lower() in {"hostname", "username", "api_key", "token"}:
                continue
            components[k] = v
    key = _h(components)
    return Fingerprint(key=key, components=components)


def fingerprint_for_hermes_target(
    *,
    model: Optional[str],
    base_url: str,
    reasoning_mode: str = "from_config",
) -> Fingerprint:
    """Shared Lite-cache fingerprint for status + check.

    Must stay identical across commands so status can see cached Lite results.
    Uses config-resolved model/base_url only (no live detect) — cheap and stable.
    """
    return build_fingerprint(
        model=model,
        base_url=base_url,
        reasoning_mode=reasoning_mode,
    )
