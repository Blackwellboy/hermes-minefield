"""The numbered ``/minefield`` menu.

``/minefield`` on its own shows it; ``/minefield <number> [args]`` runs an item
exactly as if its subcommand had been typed, so every guard (``--base-url`` is
CLI-only, the Doctor needs ``--yes``, nothing uploads without approval) still
applies. Each item says what it touches before anything runs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    key: str
    command: str  # the subcommand this number stands for
    title: str
    touches: str  # nothing | your Hermes files | the model endpoint: up to N requests
    example: str  # what to type


MENU: tuple[Item, ...] = (
    Item(
        "1",
        "check",
        "Quick check of the model Hermes is using",
        "the model endpoint: up to 5 requests",
        "/minefield 1",
    ),
    Item(
        "2",
        "wtf",
        "Something weird just happened: explain the last few minutes",
        "nothing (reads this session's flight recorder)",
        "/minefield 2   or   /minefield 2 10m",
    ),
    Item(
        "3",
        "guide",
        "Look up a symptom in the trap registry",
        "nothing (offline)",
        "/minefield 3 empty content after a tool call",
    ),
    Item(
        "4",
        "scan",
        "Scan my Hermes config for known traps",
        "your Hermes config file (read-only)",
        "/minefield 4",
    ),
    Item(
        "5",
        "doctor",
        "Full Doctor on the model endpoint",
        "the model endpoint: dozens of requests, only after you add --yes",
        "/minefield 5   (shows the plan)   then   /minefield 5 --yes",
    ),
    Item("6", "status", "What Minefield sees: endpoint, cache, recorder", "nothing", "/minefield 6"),
    Item(
        "7",
        "issues",
        "My saved incidents and reported issues",
        "nothing (GitHub only with --refresh)",
        "/minefield 7",
    ),
    Item(
        "8",
        "contribute",
        "Report a trap: a sanitized draft from an incident, sent to Minefield only when you approve",
        "nothing (a local draft; never uploads without your explicit approval)",
        "/minefield 8",
    ),
    Item(
        "9",
        "update",
        "Update Minefield: what you have, what is newest",
        "nothing; --check asks PyPI and GitHub (read-only); installing is terminal-only (--yes)",
        "/minefield 9   or   /minefield 9 --check",
    ),
)

BY_KEY = {item.key: item for item in MENU}


def render() -> str:
    lines = ["Model Serving Minefield", ""]
    for item in MENU:
        lines.append(f"  {item.key}  {item.title}   (/minefield {item.command})")
        lines.append(f"       touches: {item.touches}")
        lines.append(f"       type:    {item.example}")
    lines += ["", "Type /minefield <number>. All commands and flags: /minefield help"]
    return "\n".join(lines)


def translate(parts: list[str]) -> list[str]:
    """``["3", "empty", "content"]`` -> ``["guide", "empty", "content"]``; others unchanged."""
    if parts and parts[0] in BY_KEY:
        return [BY_KEY[parts[0]].command, *parts[1:]]
    return parts
