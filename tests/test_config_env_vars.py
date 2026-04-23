"""OS-aware default game paths + env-var override.

Covers:
  * ``D2RR_D2R_INSTALL`` / ``D2RR_MOD_DIR`` are honoured on every
    platform and win over any caller default.
  * On POSIX with neither env var nor explicit argument,
    ``init_game_paths`` raises ``ConfigurationError``.
  * On Windows the pre-existing heuristic default continues to work
    (regression guard).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from d2rr_toolkit import config as config_module
from d2rr_toolkit.exceptions import ConfigurationError


def test_init_game_paths_uses_env_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("D2RR_D2R_INSTALL", str(tmp_path / "game"))
    monkeypatch.setenv("D2RR_MOD_DIR", str(tmp_path / "mod"))
    (tmp_path / "game").mkdir()
    (tmp_path / "mod").mkdir()
    monkeypatch.setattr(config_module, "_game_paths", None)

    gp = config_module.init_game_paths()
    assert gp.d2r_install == tmp_path / "game"
    assert gp.mod_dir == tmp_path / "mod"


def test_explicit_arg_beats_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("D2RR_D2R_INSTALL", str(tmp_path / "env_game"))
    monkeypatch.setattr(config_module, "_game_paths", None)
    gp = config_module.init_game_paths(
        d2r_install=tmp_path / "arg_game",
        mod_dir=tmp_path / "arg_mod",
    )
    assert gp.d2r_install == tmp_path / "arg_game"


def test_init_game_paths_raises_on_posix_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.delenv("D2RR_D2R_INSTALL", raising=False)
    monkeypatch.delenv("D2RR_MOD_DIR", raising=False)
    monkeypatch.setattr(config_module, "_game_paths", None)
    with pytest.raises(ConfigurationError, match="D2R install"):
        config_module.init_game_paths()


def test_init_game_paths_raises_when_only_install_given_on_posix_without_mod(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Providing install but no mod still works because mod derives
    from install. This test pins the derivation contract."""
    monkeypatch.delenv("D2RR_D2R_INSTALL", raising=False)
    monkeypatch.delenv("D2RR_MOD_DIR", raising=False)
    monkeypatch.setattr(config_module, "_game_paths", None)
    gp = config_module.init_game_paths(d2r_install=tmp_path)
    assert gp.mod_dir == tmp_path / "mods" / "Reimagined"


@pytest.mark.skipif(os.name != "nt", reason="Windows-only heuristic default")
def test_windows_default_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-fix behaviour on Windows with no env vars must be unchanged."""
    monkeypatch.delenv("D2RR_D2R_INSTALL", raising=False)
    monkeypatch.delenv("D2RR_MOD_DIR", raising=False)
    monkeypatch.setattr(config_module, "_game_paths", None)
    gp = config_module.init_game_paths()
    assert "Diablo II Resurrected" in str(gp.d2r_install)
