"""Verify an isolated --target wheel install, outside the checkout imports."""
import importlib.resources
from pathlib import Path
import sys

target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target))
import hermes_minefield
from hermes_minefield.service.workspace import Workspace
import shared_contracts

assert Path(hermes_minefield.__file__).is_relative_to(target)
assert Path(shared_contracts.__file__).is_relative_to(target)
assert importlib.resources.files('hermes_minefield').joinpath('resources/SKILL.md').is_file()
assert Workspace().preview(['request_validation'])['approval_available'] is False
print('INSTALLED_WHEEL_AGENT_RESOURCES_PASS; native halves require unified zip')
