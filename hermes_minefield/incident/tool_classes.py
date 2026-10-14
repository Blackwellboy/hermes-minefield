"""Tool classes mirrored from Hermes's own loop guardrails.

Source: hermes-agent ``agent/tool_guardrails.py`` @ d350422b. The live sets are
used when importable (same Hermes process), else this vendored copy.
"""

from __future__ import annotations

_IDEMPOTENT = frozenset(
    {
        "read_file",
        "search_files",
        "web_search",
        "web_extract",
        "session_search",
        "skill_view",
        "skills_list",
        "browser_snapshot",
        "browser_console",
        "browser_get_images",
        "mcp_filesystem_read_file",
        "mcp_filesystem_read_text_file",
        "mcp_filesystem_read_multiple_files",
        "mcp_filesystem_list_directory",
        "mcp_filesystem_list_directory_with_sizes",
        "mcp_filesystem_directory_tree",
        "mcp_filesystem_get_file_info",
        "mcp_filesystem_search_files",
    }
)
_REPEATABLE = frozenset({"process_manage"})
_REPEATABLE_SUFFIXES = ("_get_result", "_poll")

try:  # pragma: no cover - depends on the installed Hermes
    from agent.tool_guardrails import IDEMPOTENT_TOOL_NAMES as _LIVE_IDEMPOTENT

    IDEMPOTENT_TOOL_NAMES = frozenset(_LIVE_IDEMPOTENT)
except Exception:
    IDEMPOTENT_TOOL_NAMES = _IDEMPOTENT

try:  # pragma: no cover - depends on the installed Hermes
    from agent.tool_guardrails import STALL_GUARD_REPEATABLE_TOOLS as _LIVE_REPEATABLE

    REPEATABLE_TOOL_NAMES = frozenset(_LIVE_REPEATABLE)
except Exception:
    REPEATABLE_TOOL_NAMES = _REPEATABLE


def is_idempotent(tool: str) -> bool:
    return tool in IDEMPOTENT_TOOL_NAMES


def is_poller(tool: str) -> bool:
    """Legitimately re-invoked with identical args (Hermes never flags these)."""
    return tool in REPEATABLE_TOOL_NAMES or tool.endswith(_REPEATABLE_SUFFIXES)
