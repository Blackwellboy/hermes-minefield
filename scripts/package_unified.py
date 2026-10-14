"""Build a review-only unified plugin zip from an explicit source allowlist.

Does not install, publish, include collector state, or execute package hooks.
"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def build(destination):
    root = Path(__file__).resolve().parents[1]
    files = []
    for name in ("hermes_minefield", "shared_contracts", "dashboard", "desktop", "skills"):
        files.extend(
            p
            for p in (root / name).rglob("*")
            if p.is_file() and p.suffix in {".py", ".md", ".js", ".json"} and "__pycache__" not in p.parts
        )
    files.extend(
        root / name for name in ("__init__.py", "plugin.yaml", "pyproject.toml", "README.md", "LICENSE")
    )
    manifest = {
        str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(manifest):
            info = zipfile.ZipInfo("hermes-minefield/" + name, date_time=(2026, 10, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (root / name).read_bytes())
        info = zipfile.ZipInfo("hermes-minefield/SOURCE_SHA256.json", date_time=(2026, 10, 14, 0, 0, 0))
        archive.writestr(info, json.dumps(manifest, sort_keys=True, indent=2))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(build(parser.parse_args().output))
