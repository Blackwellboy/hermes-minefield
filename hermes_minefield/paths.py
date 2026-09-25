"""Local storage paths under HERMES_HOME, created private (0700 dirs, 0600 files)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def hermes_home() -> Path:
    """Hermes's own resolution first (context-local/profile override → HERMES_HOME →
    default); env/default fallback only when Hermes isn't importable (tests, tools)."""
    try:
        from hermes_constants import get_hermes_home
    except ImportError:
        pass
    else:
        try:
            return Path(get_hermes_home()).expanduser().resolve()
        except Exception:
            pass
    raw = os.environ.get("HERMES_HOME") or os.environ.get("HERMES_HOME_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def _private_dir(path: Path) -> Path:
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass  # e.g. Windows / foreign-owned parent
    return path


def minefield_root() -> Path:
    return _private_dir(hermes_home() / "minefield")


def recorder_dir() -> Path:
    return _private_dir(minefield_root() / "recorder")


def incidents_dir() -> Path:
    return _private_dir(minefield_root() / "incidents")


def cache_dir() -> Path:
    return _private_dir(minefield_root() / "cache")


def candidates_dir() -> Path:
    return _private_dir(minefield_root() / "candidates")


def drafts_dir() -> Path:
    return _private_dir(minefield_root() / "drafts")


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically with mode 0600.

    Readers see the old file or the new one, never a half-written file, even if
    the process dies mid-write or two processes write at once (last one wins).
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
