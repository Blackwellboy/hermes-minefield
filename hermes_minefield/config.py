"""Plugin configuration (Hermes-local, not Minefield core)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


DEFAULT_LITE_MAX_REQUESTS = 5
DEFAULT_RECORDER_RETENTION_SECONDS = 600  # ~10 minutes
DEFAULT_RECORDER_MAX_EVENTS = 5000
DEFAULT_RECORDER_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB hard ceiling
DEFAULT_AUTO_LITE = "false"  # false | prompt | true — conservative default


# Submission targets must be user-selected or allowlisted. Never from model output.
DEFAULT_REPO_ALLOWLIST: tuple[str, ...] = (
    "Blackwellboy/model-serving-minefield",
    "NousResearch/hermes-agent",
    "ggerganov/llama.cpp",
)


@dataclass
class MinefieldPluginConfig:
    auto_lite: str = DEFAULT_AUTO_LITE
    lite_max_requests: int = DEFAULT_LITE_MAX_REQUESTS
    recorder_retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS
    recorder_max_events: int = DEFAULT_RECORDER_MAX_EVENTS
    recorder_max_bytes: int = DEFAULT_RECORDER_MAX_BYTES
    repo_allowlist: tuple[str, ...] = DEFAULT_REPO_ALLOWLIST
    fingerprint_cache_ttl_days: int = 30

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]] = None) -> "MinefieldPluginConfig":
        data = data or {}
        section = data
        if "minefield" in data and isinstance(data["minefield"], Mapping):
            section = data["minefield"]
        elif "plugins" in data and isinstance(data["plugins"], Mapping):
            entries = data["plugins"].get("entries") or {}
            if isinstance(entries, Mapping):
                for key in ("hermes-minefield", "minefield"):
                    if key in entries and isinstance(entries[key], Mapping):
                        section = entries[key]
                        break
        allow = section.get("repo_allowlist") or section.get("github_allowlist")
        if isinstance(allow, Sequence) and not isinstance(allow, (str, bytes)):
            allow_t = tuple(str(x) for x in allow)
        else:
            allow_t = DEFAULT_REPO_ALLOWLIST
        auto = str(section.get("auto_lite", DEFAULT_AUTO_LITE)).strip().lower()
        if auto not in {"false", "prompt", "true", "never", "always"}:
            auto = DEFAULT_AUTO_LITE
        if auto == "never":
            auto = "false"
        if auto == "always":
            auto = "true"
        return cls(
            auto_lite=auto,
            lite_max_requests=int(section.get("lite_max_requests", DEFAULT_LITE_MAX_REQUESTS)),
            recorder_retention_seconds=int(
                section.get("recorder_retention_seconds", DEFAULT_RECORDER_RETENTION_SECONDS)
            ),
            recorder_max_events=int(section.get("recorder_max_events", DEFAULT_RECORDER_MAX_EVENTS)),
            recorder_max_bytes=int(section.get("recorder_max_bytes", DEFAULT_RECORDER_MAX_BYTES)),
            repo_allowlist=allow_t,
            fingerprint_cache_ttl_days=int(
                section.get("fingerprint_cache_ttl_days", 30)
            ),
        )


def load_hermes_config() -> dict[str, Any]:
    """Best-effort load of ~/.hermes/config.yaml. Never raises."""
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


def load_plugin_config(cfg: Optional[Mapping[str, Any]] = None) -> MinefieldPluginConfig:
    return MinefieldPluginConfig.from_mapping(cfg if cfg is not None else load_hermes_config())
