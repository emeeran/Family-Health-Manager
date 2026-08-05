"""Settings.APP_VERSION must equal the version in backend/pyproject.toml.

Guards against the drift where the running app reported one version (hardcoded
in config.py) while the packaged .deb used another (read from pyproject).
pyproject.toml is now the single source (config.py reads it via tomllib).
"""

import tomllib
from pathlib import Path

import app.core.config as cfg


def test_app_version_matches_pyproject():
    pyproject = Path(cfg.__file__).resolve().parents[2] / "pyproject.toml"
    with open(pyproject, "rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    assert cfg.get_settings().APP_VERSION == expected
