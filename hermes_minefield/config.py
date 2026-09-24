"""Plugin configuration (Hermes-local, not Minefield core).

Canonical location (what Hermes's ``ctx.get_config`` / Desktop settings use)::

    plugins:
      entries:
        hermes-minefield:
          settings:
            lite_max_requests: 5

Legacy locations are still read, in order: ``plugins.entries.<id>.config``,
``plugins.entries.<id>`` itself, and a top-level ``minefield:`` block.
Bad values never raise: each falls back to its default (clamped to a safe range)
with one warning.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PLUGIN_ID = "hermes-minefield"

DEFAULT_LITE_MAX_REQUESTS = 5
DEFAULT_RECORDER_RETENTION_SECONDS = 600  # ~10 minutes
DEFAULT_RECORDER_MAX_EVENTS = 5000
DEFAULT_RECORDER_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB hard ceiling
DEFAULT_AUTO_LITE = "false"  # false | true — conservative default

# Submission targets must be user-selected or allowlisted. Never from model output.
DEFAULT_REPO_ALLOWLIST: tuple[str, ...] = (
    "Blackwellboy/model-serving-minefield",
    "NousResearch/hermes-agent",
    "ggerganov/llama.cpp",
)

# key: (default, lo, hi)
INT_SETTINGS: dict[str, tuple[int, int, int]] = {
    "lite_max_requests": (DEFAULT_LITE_MAX_REQUESTS, 0, DEFAULT_LITE_MAX_REQUESTS),
    "recorder_retention_seconds": (DEFAULT_RECORDER_RETENTION_SECONDS, 60, 86_400),
    "recorder_max_events": (DEFAULT_RECORDER_MAX_EVENTS, 100, 100_000),
    "recorder_max_bytes": (DEFAULT_RECORDER_MAX_BYTES, 64 * 1024, 256 * 1024 * 1024),
    "fingerprint_cache_ttl_days": (30, 1, 365),
    "incident_retention_days": (90, 1, 3650),
    "loop_streak_threshold": (5, 3, 50),
}
BOOL_SETTINGS: dict[str, bool] = {
    # Privacy-first: nothing leaves the machine unless the user opts in.
    "remote_dedupe": False,
    "allow_submit_from_chat": False,
    "expose_agent_tool": False,
}

_warned: set[str] = set()


def _warn_once(key: str, value: Any, default: Any) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning("hermes-minefield: invalid setting %s=%r; using %r", key, value, default)


def _int(section: Mapping[str, Any], key: str) -> int:
    default, lo, hi = INT_SETTINGS[key]
    if key not in section:
        return default
    raw = section.get(key)
    try:
        if isinstance(raw, bool):
            raise TypeError
        value = int(raw)
    except (TypeError, ValueError):
        _warn_once(key, raw, default)
        return default
    clamped = min(max(value, lo), hi)
    if clamped != value:
        _warn_once(key, raw, clamped)
    return clamped


def _bool(section: Mapping[str, Any], key: str) -> bool:
    default = BOOL_SETTINGS[key]
    raw = section.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in {"true", "yes", "1", "on"}:
        return True
    if isinstance(raw, str) and raw.strip().lower() in {"false", "no", "0", "off"}:
        return False
    _warn_once(key, raw, default)
    return default


def find_section(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The plugin's settings mapping from a whole Hermes config (see module doc)."""
    plugins = data.get("plugins")
    entries = plugins.get("entries") if isinstance(plugins, Mapping) else None
    if isinstance(entries, Mapping):
        for key in (PLUGIN_ID, "minefield"):
            entry = entries.get(key)
            if not isinstance(entry, Mapping):
                continue
            for sub in ("settings", "config"):
                if isinstance(entry.get(sub), Mapping):
                    return entry[sub]
            return entry
    if isinstance(data.get("minefield"), Mapping):
        return data["minefield"]
    return {}


@dataclass
class MinefieldPluginConfig:
    auto_lite: str = DEFAULT_AUTO_LITE
    lite_max_requests: int = DEFAULT_LITE_MAX_REQUESTS
    recorder_retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS
    recorder_max_events: int = DEFAULT_RECORDER_MAX_EVENTS
    recorder_max_bytes: int = DEFAULT_RECORDER_MAX_BYTES
    repo_allowlist: tuple[str, ...] = DEFAULT_REPO_ALLOWLIST
    fingerprint_cache_ttl_days: int = 30
    incident_retention_days: int = 90
    loop_streak_threshold: int = 5
    remote_dedupe: bool = False
    allow_submit_from_chat: bool = False
    expose_agent_tool: bool = False

    @classmethod
    def from_section(cls, section: Mapping[str, Any]) -> MinefieldPluginConfig:
        allow = section.get("repo_allowlist") or section.get("github_allowlist")
        if isinstance(allow, Sequence) and not isinstance(allow, (str, bytes)):
            allow_t = tuple(str(x) for x in allow if str(x).count("/") == 1)
        else:
            allow_t = DEFAULT_REPO_ALLOWLIST

        auto = str(section.get("auto_lite", DEFAULT_AUTO_LITE)).strip().lower()
        auto = {"never": "false", "always": "true", "prompt": "false"}.get(auto, auto)
        if section.get("auto_lite") is True:
            auto = "true"
        if auto not in {"false", "true"}:
            _warn_once("auto_lite", section.get("auto_lite"), DEFAULT_AUTO_LITE)
            auto = DEFAULT_AUTO_LITE

        return cls(
            auto_lite=auto,
            repo_allowlist=allow_t,
            **{k: _int(section, k) for k in INT_SETTINGS},
            **{k: _bool(section, k) for k in BOOL_SETTINGS},
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None = None) -> MinefieldPluginConfig:
        """Build from a whole Hermes config mapping."""
        return cls.from_section(find_section(data or {}))


def load_hermes_config() -> dict[str, Any]:
    """The active Hermes config. Never raises.

    Uses Hermes's own loader when available (profiles, managed config, env
    overrides); otherwise reads ``$HERMES_HOME/config.yaml``.
    """
    try:
        from hermes_cli.config import load_config_readonly
    except ImportError:
        pass
    else:
        try:
            data = load_config_readonly()
            if isinstance(data, Mapping):
                return dict(data)  # shallow copy; never mutate Hermes's cache
        except Exception:
            logger.debug("hermes load_config_readonly failed; falling back", exc_info=True)
    try:
        import yaml

        from .paths import hermes_home

        path = hermes_home() / "config.yaml"
        if not path.is_file():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_plugin_config(cfg: Mapping[str, Any] | None = None) -> MinefieldPluginConfig:
    try:
        return MinefieldPluginConfig.from_mapping(cfg if cfg is not None else load_hermes_config())
    except Exception:  # config must never break the plugin
        logger.warning("hermes-minefield: config unreadable; using defaults", exc_info=True)
        return MinefieldPluginConfig()
