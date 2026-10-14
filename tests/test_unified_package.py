import hashlib
import json
import zipfile

from scripts.package_unified import build


def test_unified_package_contains_real_entry_and_exact_manifest(tmp_path):
    archive = build(tmp_path / "plugin.zip")
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        for required in (
            "__init__.py",
            "plugin.yaml",
            "desktop/plugin.js",
            "dashboard/plugin_api.py",
            "hermes_minefield/resources/SKILL.md",
        ):
            assert "hermes-minefield/" + required in names
        manifest = json.loads(bundle.read("hermes-minefield/SOURCE_SHA256.json"))
        assert names == {"hermes-minefield/" + p for p in manifest} | {"hermes-minefield/SOURCE_SHA256.json"}
        for path, digest in manifest.items():
            assert hashlib.sha256(bundle.read("hermes-minefield/" + path)).hexdigest() == digest
        assert not any(p.endswith((".sqlite", ".jsonl", ".log")) for p in names)
    assert archive.read_bytes() == build(tmp_path / "repeat.zip").read_bytes()
