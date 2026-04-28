"""Game mode helpers - softcore vs. hardcore database segregation.

D2R and its Reimagined mod keep SoftCore and HardCore characters on
strictly separated storage: the shared stash itself lives in two files
(``ModernSharedStashSoftCoreV2.d2i`` and ``ModernSharedStashHardCoreV2.d2i``),
and a hardcore character whose save is deleted after death must never
trade items with a softcore character. Any tool that sits between a
save file and a database has to reproduce that separation or the user
can silently lose items in a cross-mode transfer.

This module centralises mode handling so every piece of the toolkit
(CLI, future GUI, services) uses the same vocabulary:

* :data:`GameMode` - the literal ``"softcore" | "hardcore"``.
* :func:`mode_from_character` - read ``is_hardcore`` off a parsed char.
* :func:`mode_from_stash_filename` - sniff a ``.d2i`` filename.
* :func:`default_archive_db_name` - build a mode-specific DB filename.
* :func:`default_archive_db_path` - resolve the DB file inside a base dir.
* :exc:`GameModeError` - raised when mode detection fails.
* :exc:`DatabaseModeMismatchError` - raised when a DB tagged for one
  mode is opened for the other.

The archive database and the Section 5 database share a single SQLite
file per game mode - both classes open the same file and cooperate on
the meta table. There is intentionally no separate ``default_section5``
path helper: future versions may split them, but today they live
together and exposing two paths would invite bugs.

The helpers are pure string/metadata logic with no I/O, so they are
cheap to use everywhere.
"""

import sqlite3
from pathlib import Path
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedCharacter
from d2rr_toolkit.config import resolve_save_dir

__all__ = [
    "GameMode",
    "SOFTCORE",
    "HARDCORE",
    "GameModeError",
    "DatabaseModeMismatchError",
    "META_KEY_GAME_MODE",
    "META_SCHEMA_SQL",
    "bind_database_mode",
    "mode_from_character",
    "mode_from_stash_filename",
    "default_archive_db_name",
    "default_archive_db_path",
]


#: Literal alias for the two supported game modes. Using a :class:`Literal`
#: instead of an :class:`enum.Enum` keeps callsites terse (``"softcore"``)
#: and removes the need to import a symbol everywhere - but the two
#: module-level constants below are still available for code that prefers
#: named references.
type GameMode = Literal["softcore", "hardcore"]

SOFTCORE: GameMode = "softcore"
HARDCORE: GameMode = "hardcore"


class GameModeError(ValueError):
    """Raised when a game mode cannot be determined from the given input."""


class DatabaseModeMismatchError(RuntimeError):
    """Raised when an archive database tagged for one mode is opened
    with a caller expecting the other mode.

    This is the last-line defence against mixing softcore and hardcore
    items: the database itself refuses to cooperate, so even a buggy
    script that picks the wrong file cannot cross-contaminate the two
    archives.
    """


# --------------------------------------------------------------------------- #
#  Mode detection
# --------------------------------------------------------------------------- #


def mode_from_character(character: "ParsedCharacter") -> GameMode:
    """Return the game mode of a parsed character.

    The mode is derived from the ``is_hardcore`` bit of the D2S header,
    which is set whenever the user rolls a hardcore character. The bit
    survives even after the character has died; the character's
    :attr:`died_flag` is independent.

    Args:
        character: A fully parsed :class:`~d2rr_toolkit.models.character.ParsedCharacter`.

    Returns:
        ``"hardcore"`` if the character's ``is_hardcore`` bit is set,
        otherwise ``"softcore"``.
    """
    return HARDCORE if character.header.is_hardcore else SOFTCORE


#: Canonical suffix used by the game (and by this tool) to mark the
#: SoftCore shared-stash file on disk. Matched case-insensitively.
_STASH_SOFTCORE_HINT = "softcore"
_STASH_HARDCORE_HINT = "hardcore"


def mode_from_stash_filename(path: Path | str) -> GameMode:
    """Sniff the game mode from a shared-stash filename.

    The D2R Reimagined mod ships two stash files whose names encode the
    mode directly::

        ModernSharedStashSoftCoreV2.d2i   -> softcore
        ModernSharedStashHardCoreV2.d2i   -> hardcore

    The check is case-insensitive and tolerates arbitrary prefixes or
    suffixes, so custom renames like ``backup_softcore.d2i`` still
    resolve correctly.

    Args:
        path: Path to (or name of) a ``.d2i`` shared-stash file.

    Returns:
        ``"softcore"`` or ``"hardcore"`` depending on which hint appears
        in the filename.

    Raises:
        GameModeError: If neither hint is present in the filename.
    """
    name = Path(path).name.lower()
    has_sc = _STASH_SOFTCORE_HINT in name
    has_hc = _STASH_HARDCORE_HINT in name
    if has_sc and not has_hc:
        return SOFTCORE
    if has_hc and not has_sc:
        return HARDCORE
    raise GameModeError(
        f"Cannot determine game mode from filename {Path(path).name!r}: "
        "expected the name to contain 'SoftCore' or 'HardCore'. Pass "
        "--mode explicitly to override."
    )


# --------------------------------------------------------------------------- #
#  Default filenames / paths
# --------------------------------------------------------------------------- #

#: Basename prefix shared by both archive databases. The mode-specific
#: files are :code:`<prefix>_softcore.db` and :code:`<prefix>_hardcore.db`.
#:
#: The archive (``items`` table) and the Section 5 inventory
#: (``section5_stacks`` / ``gem_pool`` / ``gem_templates`` tables) share a
#: single SQLite file per mode - so the name "archive DB" is a slight
#: misnomer, but it matches the legacy ``d2rr_archive_<mode>.db`` canonical filename.
_ARCHIVE_DB_PREFIX = "d2rr_archive"


def default_archive_db_name(mode: GameMode) -> str:
    """Return the canonical filename of the archive DB for *mode*.

    The two modes always use physically separate files so there is no
    way to cross-contaminate softcore and hardcore items even if the
    meta-table check inside :class:`ItemDatabase` is bypassed.
    """
    return f"{_ARCHIVE_DB_PREFIX}_{mode}.db"


def default_archive_db_path(
    mode: GameMode,
    base_dir: Path | None = None,
) -> Path:
    """Return the full canonical path for the mode-specific archive DB.

    The archive database lives alongside the D2RR (Reimagined-modded)
    save files by design: the DB is keyed to the user's characters
    and shared stashes, so co-locating them means a single
    ``Saved Games/.../mods/ReimaginedThree`` backup captures both the
    game state and the toolkit's archive. This is a different
    directory from the base-game D2R save dir; the toolkit never
    writes to the base-game dir.

    Args:
        mode: ``"softcore"`` or ``"hardcore"``.
        base_dir: Directory to place the DB in. Defaults to the D2R
            save directory resolved via
            :func:`d2rr_toolkit.config.resolve_save_dir` (honours
            ``D2RR_SAVE_DIR`` on every platform; Windows heuristic
            ``~/Saved Games/Diablo II Resurrected/mods/ReimaginedThree``
            otherwise).

    Raises:
        ConfigurationError: If ``base_dir`` is ``None`` and the save
            directory cannot be resolved (POSIX without
            ``D2RR_SAVE_DIR``). Never silently falls back to another
            location - callers must either set the env var, pass
            ``base_dir`` explicitly, or supply ``--db`` on the CLI.
    """
    if base_dir is None:

        base_dir = resolve_save_dir()
    return base_dir / default_archive_db_name(mode)


# --------------------------------------------------------------------------- #
#  Shared meta-table machinery for ItemDatabase / Section5Database
# --------------------------------------------------------------------------- #

#: SQL for the single-row meta table that stores the database-wide mode
#: tag. Both :class:`~d2rr_toolkit.database.item_db.ItemDatabase` and
#: :class:`~d2rr_toolkit.database.section5_db.Section5Database` run this
#: at open time so either class can be the "first" to touch a fresh file.
META_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

#: Meta-table key under which the game mode tag is persisted.
META_KEY_GAME_MODE = "game_mode"


def bind_database_mode(
    conn: sqlite3.Connection,
    expected: GameMode,
    *,
    db_path: Path | str | None = None,
) -> GameMode:
    """Write-or-validate the game mode tag on *conn*.

    On a freshly created database, inserts *expected* into the ``meta``
    table and returns it. On a pre-existing database, compares the
    stored tag against *expected* - raising
    :class:`DatabaseModeMismatchError` if they disagree.

    This helper is intentionally standalone so both
    :class:`ItemDatabase` and :class:`Section5Database` can invoke it
    from their constructors without duplicating the logic. The caller
    is responsible for having run :data:`META_SCHEMA_SQL` first.

    Args:
        conn: Open SQLite connection.
        expected: Mode the caller wants to use.
        db_path: Optional path included in the error message for
            debugging - has no effect on the logic.

    Returns:
        The effective mode (always equal to *expected* when no error
        is raised).

    Raises:
        DatabaseModeMismatchError: If a different mode is already stored.
    """
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?",
        (META_KEY_GAME_MODE,),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            (META_KEY_GAME_MODE, expected),
        )
        conn.commit()
        return expected
    # sqlite3.Row is subscriptable; plain tuple row falls back to index 0.
    stored: str = row["value"] if hasattr(row, "keys") else row[0]
    if stored != expected:
        where = f" at {db_path}" if db_path else ""
        raise DatabaseModeMismatchError(
            f"Database{where} is tagged as {stored!r} but was opened "
            f"as {expected!r}. SoftCore and HardCore items must never "
            "share a database."
        )
    # ``stored`` is one of "softcore" / "hardcore" by construction; the
    # equality check above narrows it to ``GameMode`` semantically.
    if stored == "softcore":
        return SOFTCORE
    return HARDCORE
