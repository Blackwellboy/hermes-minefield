"""Generic single-slot / concurrency guard (no private fleet assumptions)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class ConcurrencyInfo:
    known_concurrency: Optional[int]
    single_slot_likely: bool
    source: str
    detail: str


def _root_from_base(base_url: str) -> str:
    u = base_url.rstrip("/")
    if u.endswith("/v1"):
        u = u[:-3]
    return u.rstrip("/") or base_url


def probe_concurrency(base_url: str, *, timeout: float = 2.0) -> ConcurrencyInfo:
    """Best-effort concurrency probe. Prefer UNKNOWN over false safety."""
    root = _root_from_base(base_url)
    # llama.cpp /props often exposes total_slots
    for path in ("/props", "/slots"):
        url = f"{root}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(65536)
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            continue
        if path == "/props" and isinstance(data, dict):
            slots = data.get("total_slots")
            if slots is None and isinstance(data.get("default_generation_settings"), dict):
                slots = data["default_generation_settings"].get("n_slots")
            if isinstance(slots, int) and slots >= 1:
                return ConcurrencyInfo(
                    known_concurrency=slots,
                    single_slot_likely=slots == 1,
                    source="props.total_slots",
                    detail=f"total_slots={slots}",
                )
        if path == "/slots" and isinstance(data, list):
            n = len(data)
            if n >= 1:
                return ConcurrencyInfo(
                    known_concurrency=n,
                    single_slot_likely=n == 1,
                    source="slots.length",
                    detail=f"slots_len={n}",
                )

    host = urlparse(base_url).hostname or ""
    looks_local = host in {"127.0.0.1", "localhost", "::1"} or host.endswith(".local")
    return ConcurrencyInfo(
        known_concurrency=None,
        single_slot_likely=False,  # unknown ≠ assume single
        source="unknown",
        detail="UNKNOWN" + (" (local-looking endpoint)" if looks_local else ""),
    )


def doctor_guard_message(info: ConcurrencyInfo) -> str:
    if info.known_concurrency == 1 or info.single_slot_likely:
        return (
            "This diagnostic may monopolize the only inference slot and delay "
            "interactive agent traffic.\n"
            f"Detected: {info.detail} (source={info.source}).\n"
            "Re-run with --yes to confirm, or use another endpoint."
        )
    if info.known_concurrency is None:
        return (
            "Concurrency is UNKNOWN for this endpoint.\n"
            f"Detail: {info.detail}.\n"
            "Full Doctor may contend with interactive traffic if the server is "
            "single-slot. Re-run with --yes to confirm."
        )
    return ""


def requires_doctor_confirm(info: ConcurrencyInfo) -> bool:
    return info.known_concurrency == 1 or info.single_slot_likely or info.known_concurrency is None
