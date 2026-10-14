"""Optional background Lite check at session start (``auto_lite: true``).

Safety rules:
- never runs on the hook thread (daemon thread; the hook returns immediately);
- at most once per process, and only when the cached result is missing/stale;
- only when the endpoint reports >= 2 inference slots — never on single-slot or
  unknown-concurrency servers, where it would compete with the user's own turn;
- prints nothing into the chat; the result lands in the cache (``status``).
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def _run() -> None:
    try:
        from .cache import get_entry
        from .commands.check import run_check
        from .concurrency import probe_concurrency
        from .config import load_plugin_config
        from .fingerprint import fingerprint_for_hermes_target
        from .target import resolve_target

        cfg = load_plugin_config()
        target = resolve_target()
        fp = fingerprint_for_hermes_target(model=target.model, base_url=target.base_url)
        if get_entry(fp.key, ttl_days=cfg.fingerprint_cache_ttl_days):
            return
        info = probe_concurrency(target.base_url, api_key=target.api_key)
        if (info.known_concurrency or 0) < 2:
            logger.info("minefield auto_lite skipped: concurrency %s", info.detail)
            return
        out = run_check()
        logger.info("minefield auto_lite: %s", out.get("verdict"))
    except Exception:
        logger.debug("minefield auto_lite failed", exc_info=True)


def maybe_start(*, start_thread=None) -> bool:
    """Called from on_session_start. Returns True if a background check was started."""
    global _started
    from .config import load_plugin_config

    if load_plugin_config().auto_lite != "true":
        return False
    with _lock:
        if _started:
            return False
        _started = True
    (start_thread or _default_start)(_run)
    return True


def _default_start(target) -> None:
    threading.Thread(target=target, name="minefield-auto-lite", daemon=True).start()


def _reset_for_tests() -> None:
    global _started
    _started = False
