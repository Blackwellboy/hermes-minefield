"""Run a Python module in a clean home with a fail-closed network fence."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="minefield-isolated-") as tmp:
    home = Path(tmp)
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if k in os.environ}
    env.update(
        {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            "HOME": tmp,
            "USERPROFILE": tmp,
            "HERMES_HOME": str(home / "hermes"),
            "HERMES_RUNTIME_DIR": str(home / "runtime"),
            "APPDATA": str(home / "appdata"),
            "LOCALAPPDATA": str(home / "localappdata"),
            "TEMP": tmp,
            "TMP": tmp,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(root / "scripts" / "isolation"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    raise SystemExit(subprocess.call([sys.executable, "-m", *sys.argv[1:]], cwd=root, env=env))
