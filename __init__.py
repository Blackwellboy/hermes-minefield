"""Directory-plugin entry for ~/.hermes/plugins/hermes-minefield/.

Hermes loads this file as a package under ``hermes_plugins.<slug>``.
We also support bare imports during local tests by putting this directory
on ``sys.path`` so ``hermes_minefield`` resolves as a top-level package.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hermes_minefield.plugin import register  # noqa: E402

__all__ = ["register"]
