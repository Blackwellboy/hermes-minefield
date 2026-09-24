"""Resolve the active Hermes model endpoint (and its credentials) without inventing URLs."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .config import load_hermes_config

logger = logging.getLogger(__name__)

# Minefield probes OpenAI-compatible chat-completions servers (llama.cpp, vLLM, SGLang, …).
PROBEABLE_API_MODES = frozenset({"chat_completions"})


@dataclass(frozen=True)
class ResolvedTarget:
    base_url: str
    model: str | None
    provider: str | None
    source: str
    notes: tuple[str, ...] = ()
    # Never printed, cached or persisted (repr=False keeps it out of reprs/logs).
    api_key: str | None = field(default=None, repr=False)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def _hermes_runtime(model: str | None) -> Mapping[str, Any] | None:
    """Hermes's own provider/credential resolution, or None if unavailable/failed."""
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider
    except ImportError:
        return None
    try:
        rt = resolve_runtime_provider(target_model=model)
    except Exception:
        logger.debug("resolve_runtime_provider failed; falling back to config", exc_info=True)
        return None
    return rt if isinstance(rt, Mapping) else None


def _key(rt: Mapping[str, Any] | None) -> str | None:
    key = rt.get("api_key") if rt else None
    # Hermes may return a callable key provider; never invoke arbitrary callables here.
    return key if isinstance(key, str) and key else None


def _config_target(
    model: str | None, config: Mapping[str, Any] | None
) -> tuple[str | None, str | None, str | None, list[str]]:
    notes: list[str] = []
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
    return url, mid, provider, notes


def resolve_target(
    *,
    base_url: str | None = None,
    model: str | None = None,
    config: Mapping[str, Any] | None = None,
    use_hermes_runtime: bool = True,
) -> ResolvedTarget:
    """Resolve chat-completions base URL, model id and credentials.

    - Explicit ``base_url`` wins. Hermes credentials are attached only when that
      URL is exactly Hermes's own runtime endpoint (never sent to another host).
    - Otherwise Hermes's runtime provider resolution is used (named providers,
      env config, credential pools), falling back to the ``model:`` config block.
    - Never invents a URL; raises ValueError when none is configured.
    """
    cfg_url, cfg_model, cfg_provider, notes = _config_target(model, config)
    mid = _as_str(model) or cfg_model
    rt = _hermes_runtime(mid) if use_hermes_runtime and config is None else None

    if base_url:
        key = None
        if rt and _norm(rt.get("base_url")) == _norm(base_url):
            key = _key(rt)
            notes.append("credentials_from_hermes_runtime")
        return ResolvedTarget(
            base_url=_norm(base_url),
            model=mid,
            provider=None,
            source="explicit",
            notes=tuple(notes),
            api_key=key,
        )

    rt_url = _as_str(rt.get("base_url")) if rt else None
    if rt_url:
        mode = _as_str(rt.get("api_mode"))
        if mode and mode not in PROBEABLE_API_MODES:
            provider = _as_str(rt.get("provider")) or "?"
            raise ValueError(
                f"Hermes's active provider ({provider}) uses api_mode '{mode}', not an OpenAI-compatible "
                "chat-completions API, so Minefield can't probe it. Pass --base-url <.../v1> to test an "
                "OpenAI-compatible endpoint, or set model.base_url."
            )
        return ResolvedTarget(
            base_url=_norm(rt_url),
            model=mid,
            provider=_as_str(rt.get("provider")) or cfg_provider,
            source="hermes_runtime",
            notes=tuple(notes),
            api_key=_key(rt),
        )

    if not cfg_url:
        raise ValueError(
            "No model base_url configured. Pass --base-url or set model.base_url in Hermes config."
        )
    return ResolvedTarget(
        base_url=_norm(cfg_url),
        model=mid,
        provider=cfg_provider,
        source="hermes_config",
        notes=tuple(notes),
    )
