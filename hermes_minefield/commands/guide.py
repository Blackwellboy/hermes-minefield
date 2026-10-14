"""``/minefield guide <symptom>``: match a plain-words symptom against the registry. Offline."""

from __future__ import annotations

import io
from typing import Any

from .. import verdict as V

NEEDS_NEWER_CORE = (
    "minefield: this command needs model-serving-minefield 0.2.1 or newer (the installed core "
    "has no {what}). Upgrade it in the Python that runs Hermes: "
    'pip install -U "model-serving-minefield>=0.2.1,<0.3"'
)


def run_guide(*, symptom: list[str] | str | None = None, limit: int = 5) -> dict[str, Any]:
    text = " ".join(symptom) if isinstance(symptom, list) else (symptom or "")
    text = text.strip()
    if not text:
        return {
            "ok": False,
            "text": "minefield: say what you are seeing, e.g. /minefield guide streaming replies are blank",
        }
    from minefield.matching import diagnose
    from minefield.registry import load_registry

    try:
        from minefield.render import render_diagnosis
    except ImportError:
        msg = NEEDS_NEWER_CORE.format(what="text renderer")
        return {"ok": False, "verdict": V.UNKNOWN, "text": msg + "\n\n" + V.line(V.UNKNOWN, "not run")}

    result = diagnose(load_registry(), text, limit=max(1, limit))
    # A StringIO stream keeps colour codes out of chat.
    rendered = render_diagnosis(result, limit=max(1, limit), stream=io.StringIO())
    # A lookup is not a test of this machine, so it carries no PASS/FAIL/UNKNOWN verdict.
    return {
        "ok": True,
        "symptom": text,
        "matches": len(result.get("matches") or []),
        "text": rendered.rstrip(),
    }
