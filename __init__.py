"""Directory-plugin entry for ~/.hermes/plugins/hermes-minefield/.

Hermes imports this directory as a package (``hermes_plugins.<slug>``), so the
real code is reached with a relative import. Tooling that imports this file
standalone (e.g. pytest's rootdir handling) falls back to the installed
``hermes_minefield`` package. The plugin never modifies ``sys.path``.
"""

from __future__ import annotations

if __package__:
    from .hermes_minefield.plugin import register
else:  # pragma: no cover - standalone import, not the Hermes loader path
    from hermes_minefield.plugin import register

__all__ = ["register"]
