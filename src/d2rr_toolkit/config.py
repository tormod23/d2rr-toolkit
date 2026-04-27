"""Centralized game path configuration for D2RR Toolkit.

Terminology - **D2R** is the base game (Diablo II: Resurrected,
unmodded). **D2RR** is D2R with the Reimagined mod installed; this
toolkit operates exclusively on D2RR saves (it is **not** compatible
with plain D2R because Reimagined adds new items, stats, and
mechanics).

Three directories matter to the toolkit:

  1. **D2R Install** -- Diablo II: Resurrected base-game installation
     root. Contains the CASC archive (base-game data + vanilla
     sprites); the toolkit reads it read-only as the Iron-Rule
     fallback behind the Reimagined mod overlay.
     Default: ``C:\\Program Files (x86)\\Diablo II Resurrected``
  2. **Mod Directory** -- Reimagined mod root (installed as a
     subdirectory of the D2R install). Contains modded game data
     (excel, sprites, strings).
     Default: ``<D2R install>\\mods\\Reimagined``
  3. **D2RR Save Directory** -- where the Reimagined-modded game
     keeps the user's .d2s / .d2i save files AND where the toolkit
     stores its archive SQLite databases (so backing up the save
     directory also backs up the archive). This is a *different*
     directory from the base-game save dir - D2R saves live in
     ``~/Saved Games/Diablo II Resurrected/`` and the toolkit must
     never touch those.
     Default (Windows):
     ``~\\Saved Games\\Diablo II Resurrected\\mods\\ReimaginedThree``

D2R Install + Mod Dir are read-only; the D2RR save directory is the
only location the toolkit writes to.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from d2rr_toolkit.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# ── Default paths ─────────────────────────────────────────────────────────────
#
# The env-var contract:
#   * ``D2RR_D2R_INSTALL`` overrides every other source of the D2R
#     install root, on every platform.
#   * ``D2RR_MOD_DIR`` overrides every other source of the mod root.
#   * ``D2RR_SAVE_DIR`` overrides every other source of the D2RR save
#     directory (where the Reimagined-modded game's .d2s / .d2i files
#     live AND where the archive databases are stored by default).
#   * On Windows only, if no env var + no caller arg is provided,
#     known-good heuristic defaults are returned for all three.
#   * On POSIX, no heuristic default exists -- callers MUST either
#     set the env var or pass an explicit argument, otherwise
#     ``init_game_paths`` / ``resolve_save_dir`` raise
#     :class:`ConfigurationError`.
#
# ``DEFAULT_D2R_INSTALL`` / ``DEFAULT_MOD_DIR`` / ``DEFAULT_SAVE_DIR``
# remain module-level constants for back-compat with any external
# consumer that imports them directly, but they now resolve to ``None``
# on POSIX.

_WINDOWS_D2R_INSTALL = Path(r"C:\Program Files (x86)\Diablo II Resurrected")
_WINDOWS_SAVE_DIR_SUFFIX = (
    Path("Saved Games") / "Diablo II Resurrected" / "mods" / "ReimaginedThree"
)


def _default_d2r_install() -> Path | None:
    """Resolve the D2R install default path, honouring env + OS."""
    env = os.environ.get("D2RR_D2R_INSTALL")
    if env:
        return Path(env)
    if os.name == "nt":
        return _WINDOWS_D2R_INSTALL
    return None


def _default_mod_dir(d2r_install: Path | None = None) -> Path | None:
    """Resolve the mod-dir default, honouring env + derivation from install."""
    env = os.environ.get("D2RR_MOD_DIR")
    if env:
        return Path(env)
    if d2r_install is None:
        d2r_install = _default_d2r_install()
    if d2r_install is None:
        return None
    return d2r_install / "mods" / "Reimagined"


def _default_save_dir() -> Path | None:
    """Resolve the D2RR save directory default path.

    Resolution order:
      1. ``D2RR_SAVE_DIR`` environment variable.
      2. Windows heuristic:
         ``%USERPROFILE%\\Saved Games\\Diablo II Resurrected\\mods\\ReimaginedThree``.
      3. ``None`` on POSIX without the env var - callers must raise.

    This is the **Reimagined-modded** save directory, not the base-
    game save directory. The Reimagined mod stores ``.d2s`` character
    saves, ``.d2i`` shared-stash files, and ``CubeContents.d2s`` in a
    dedicated ``mods/ReimaginedThree/`` subdirectory so they never
    mix with plain D2R saves. The toolkit also stores its archive
    SQLite databases here by default so that any save-directory
    backup automatically captures the archive.
    """
    env = os.environ.get("D2RR_SAVE_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        return Path.home() / _WINDOWS_SAVE_DIR_SUFFIX
    return None


def resolve_save_dir() -> Path:
    """Return the D2RR save directory, raising if it cannot be resolved.

    Unlike :func:`_default_save_dir` (which returns ``None`` on POSIX
    without ``D2RR_SAVE_DIR``), this helper raises
    :class:`ConfigurationError` with a clear message so the caller
    never silently falls back to an unrelated location (in particular,
    not the base-game D2R save dir).
    """
    path = _default_save_dir()
    if path is None:
        raise ConfigurationError(
            "D2RR save directory is not configured. Set the "
            "D2RR_SAVE_DIR environment variable to the directory where "
            "D2R Reimagined stores your .d2s / .d2i files "
            "(typically "
            "'~/Saved Games/Diablo II Resurrected/mods/ReimaginedThree' "
            "on Windows - note the 'mods/ReimaginedThree' subdirectory; "
            "this is NOT the same as the base-game D2R save dir)."
        )
    return path


#: Module-level defaults (Windows heuristic or ``None`` on POSIX /
#: when the corresponding env var is unset).
DEFAULT_D2R_INSTALL: Path | None = _default_d2r_install()
DEFAULT_MOD_DIR: Path | None = _default_mod_dir(DEFAULT_D2R_INSTALL)
DEFAULT_SAVE_DIR: Path | None = _default_save_dir()


@dataclass
class GamePaths:
    """Resolved paths to all game data sources.

    Built from the two user-provided base paths (D2R install + mod directory).
    All paths are read-only - no writes to game directories.
    """

    # ── User-provided base paths ──────────────────────────────────────────
    # Defaults resolve via _default_* helpers so env vars take effect
    # on every construction, not just at module import time.
    d2r_install: Path = field(default_factory=lambda: _default_d2r_install() or Path())
    mod_dir: Path = field(default_factory=lambda: _default_mod_dir() or Path())

    # ── Derived paths (set by resolve()) ──────────────────────────────────

    # Reimagined game data (excel txt files)
    reimagined_excel: Path = field(default=Path(), init=False)
    # Reimagined strings (JSON localization files)
    reimagined_strings: Path = field(default=Path(), init=False)
    # Mod's MPQ-like directory (Reimagined.mpq/)
    mod_mpq: Path = field(default=Path(), init=False)
    # DC6 legacy sprites (mod-specific items)
    mod_dc6_items: Path = field(default=Path(), init=False)
    # HD sprites directory (mod-specific items)
    mod_hd_items: Path = field(default=Path(), init=False)
    # HD items.json mapping (base item -> asset path)
    mod_items_json: Path = field(default=Path(), init=False)
    # HD uniques.json mapping (unique snake_name -> asset path per tier)
    mod_uniques_json: Path = field(default=Path(), init=False)
    # HD sets.json mapping (set-item snake_name -> asset path per tier)
    mod_sets_json: Path = field(default=Path(), init=False)

    def __post_init__(self) -> None:
        self.resolve()

    def resolve(self) -> None:
        """Derive all sub-paths from the two base directories."""
        self.mod_mpq = self.mod_dir / "Reimagined.mpq"
        self.reimagined_excel = self.mod_mpq / "data" / "global" / "excel"
        self.reimagined_strings = self.mod_mpq / "data" / "local" / "lng" / "strings"
        self.mod_dc6_items = self.mod_mpq / "data" / "global" / "items"
        self.mod_hd_items = self.mod_mpq / "data" / "hd" / "global" / "ui" / "items"
        self.mod_items_json = self.mod_mpq / "data" / "hd" / "items" / "items.json"
        self.mod_uniques_json = self.mod_mpq / "data" / "hd" / "items" / "uniques.json"
        self.mod_sets_json = self.mod_mpq / "data" / "hd" / "items" / "sets.json"

    def validate(self) -> list[str]:
        """Return a list of validation warnings (empty = all good)."""
        warnings = []
        if not self.d2r_install.is_dir():
            warnings.append(f"D2R install not found: {self.d2r_install}")
        if not self.mod_mpq.is_dir():
            warnings.append(f"Mod directory not found: {self.mod_mpq}")
        if not self.reimagined_excel.is_dir():
            warnings.append(f"Reimagined excel data not found: {self.reimagined_excel}")
        return warnings

    def log_status(self) -> None:
        """Log the resolved paths and their status."""
        logger.info(
            "D2R install: %s (%s)",
            self.d2r_install,
            "OK" if self.d2r_install.is_dir() else "MISSING",
        )
        logger.info("Mod dir: %s (%s)", self.mod_dir, "OK" if self.mod_mpq.is_dir() else "MISSING")
        logger.info(
            "Excel: %s (%s)",
            self.reimagined_excel,
            "OK" if self.reimagined_excel.is_dir() else "MISSING",
        )
        logger.info(
            "Strings: %s (%s)",
            self.reimagined_strings,
            "OK" if self.reimagined_strings.is_dir() else "MISSING",
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_game_paths: GamePaths | None = None


def init_game_paths(d2r_install: Path | None = None, mod_dir: Path | None = None) -> GamePaths:
    """Initialize and return the global GamePaths singleton.

    Resolution order for each path:
        1. Explicit argument (``d2r_install`` / ``mod_dir``).
        2. Environment variable (``D2RR_D2R_INSTALL`` /
           ``D2RR_MOD_DIR``).
        3. OS-specific heuristic (Windows only).

    Raises:
        ConfigurationError: if no path can be resolved for either
            base directory (typically on POSIX without env vars).

    Args:
        d2r_install: D2R installation root. Uses env / OS default if None.
        mod_dir: Reimagined mod root. Uses env / derived default if None.
    """
    global _game_paths
    resolved_install = d2r_install or _default_d2r_install()
    if resolved_install is None:
        raise ConfigurationError(
            "D2R install path is not configured. "
            "Set the D2RR_D2R_INSTALL environment variable or pass "
            "d2r_install= explicitly."
        )
    resolved_mod = mod_dir or _default_mod_dir(resolved_install)
    if resolved_mod is None:
        raise ConfigurationError(
            "Mod directory is not configured. "
            "Set the D2RR_MOD_DIR environment variable or pass "
            "mod_dir= explicitly."
        )
    _game_paths = GamePaths(
        d2r_install=resolved_install,
        mod_dir=resolved_mod,
    )
    _game_paths.log_status()
    warnings = _game_paths.validate()
    for w in warnings:
        logger.warning(w)
    return _game_paths


def get_game_paths() -> GamePaths:
    """Return the global GamePaths singleton. Must call init_game_paths() first."""
    if _game_paths is None:
        return init_game_paths()
    return _game_paths
