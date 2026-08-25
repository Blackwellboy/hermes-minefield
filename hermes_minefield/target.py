"""Resolve the active Hermes model endpoint without inventing URLs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .config import load_hermes_config


@dataclass(frozen=True)
class ResolvedTarget:
    base_url: str
    model: Optional[str]
    provider: Optional[str]
    source: str
    notes: tuple[str, ...] = ()


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def resolve_target(
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> ResolvedTarget:
    """Resolve chat-completions base URL + model id.

    Explicit caller overrides win. Otherwise read Hermes ``model`` config.
    Never invents a remote URL when unset.
    """
    notes: list[str] = []
    if base_url:
        return ResolvedTarget(
            base_url=base_url.rstrip("/"),
            model=_as_str(model),
            provider=None,
            source="explicit",
            notes=tuple(notes),
        )

    cfg = dict(config) if config is not None else load_hermes_config()
    model_cfg = cfg.get("model") if isinstance(cfg.get("model"), Mapping) else {}
    url = _as_str(model_cfg.get("base_url"))
    mid = _as_str(model) or _as_str(model_cfg.get("default")) or _as_str(model_cfg.get("name"))
    provider = _as_str(model_cfg.get("provider"))

    if not url and provider:
        providers = cfg.get("providers") if isinstance(cfg.get("providers"), Mapping) else {}
        pblock = providers.get(provider) if isinstance(providers, Mapping) else None
        if isinstance(pblock, Mapping):
            url = _as_str(pblock.get("base_url")) or _as_str(pblock.get("baseUrl"))
            if url:
                notes.append(f"resolved_from_provider:{provider}")

    if not url:
        raise ValueError(
            "No model base_url configured. Pass --base-url or set model.base_url in Hermes config."
        )

    return ResolvedTarget(
        base_url=url.rstrip("/"),
        model=mid,
        provider=provider,
        source="hermes_config",
        notes=tuple(notes),
    )
