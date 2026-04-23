"""CASC archive reader for Diablo II Resurrected.

Pure-Python implementation based on CascLib algorithms. No native
dependencies beyond Pillow (optional, for sprite decoding only).

This adapter wraps the on-disk CASC storage that ships with the D2R
installation. It exposes a read-only view of the asset tree, resolving
TVFS paths to content keys and decoding BLTE-encoded blobs on demand.

IRON RULE - The Only Sanctioned Way to Read Game Data Files
===========================================================

Every file that lives in the D2R Resurrected data tree - itemtypes.txt,
armor.txt, uniqueitems.txt, any .sprite, any strings JSON, absolutely
anything - MUST be read through :meth:`CASCReader.read_file`. That
method implements the two-source rule:

  1. **Reimagined Mod install** (disk, the only authoritative truth)
     e.g. ``C:/Program Files (x86)/Diablo II Resurrected/mods/Reimagined/Reimagined.mpq/data/global/excel/itemtypes.txt``
  2. **D2R Resurrected CASC archive** (fallback, only when the file is
     NOT present in the mod install)
     addressed as ``data:data/global/excel/itemtypes.txt``

Both sources share the **same relative path** under their respective
roots, so a single CASC-style path string addresses both. Any other
mechanism (ad-hoc ``excel_base / "reimagined"`` / ``"original"``
subdir lookups, pre-extracted file caches, disk-layout heuristics)
creates parallel sources of truth that will drift apart and break the
mod-first guarantee. Don't.

Usage::

    from d2rr_toolkit.adapters.casc import get_game_data_reader

    reader = get_game_data_reader()     # process-wide singleton
    bytes_ = reader.read_file("data:data/global/excel/itemtypes.txt")
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from d2rr_toolkit.adapters.casc.reader import CASCReader

__all__ = [
    "CASCReader",
    "get_game_data_reader",
    "reset_game_data_reader",
    "read_game_data_bytes",
    "read_game_data_rows",
    "list_game_data_files",
]

_logger = logging.getLogger(__name__)

_reader: CASCReader | None = None


def get_game_data_reader() -> CASCReader:
    """Return the process-wide :class:`CASCReader` for game data access.

    On first call the reader is constructed with the Reimagined mod
    install as ``mod_dir`` and the D2R Resurrected install root as
    ``game_dir`` - the exact combination that makes
    :meth:`CASCReader.read_file` honour the Iron Rule (mod first,
    CASC fallback). Every subsequent call returns the same instance.

    Callers who never need to read any game data file directly can
    still use the instance-returning form below; callers who only
    need one-off reads should prefer ``get_game_data_reader().read_file(path)``
    over constructing their own CASCReader.
    """
    global _reader
    if _reader is None:
        from d2rr_toolkit.config import get_game_paths

        gp = get_game_paths()
        _reader = CASCReader(game_dir=gp.d2r_install, mod_dir=gp.mod_mpq)
    return _reader


def reset_game_data_reader() -> None:
    """Reset the singleton. Exposed for tests that want a clean slate."""
    global _reader
    _reader = None


# ── High-level game-data helpers ────────────────────────────────────────────
# Every toolkit loader that reads a Reimagined / D2R data file MUST go
# through one of the helpers below. They encapsulate the Iron Rule:
# Reimagined mod install first, D2R Resurrected CASC archive as the
# single fallback, no other sources.
#
# Direct ``pathlib`` arithmetic against an ``excel_base`` parameter is
# forbidden - the loader won't honour the mod/CASC priority and silent
# drift between the two sources will eat the day of whoever debugs the
# resulting ghost. See memory note ``project_data_source_iron_rule``.


def read_game_data_bytes(casc_path: str) -> bytes | None:
    """Return the raw bytes of a game-data file, or ``None`` if neither
    the Reimagined mod install nor the D2R CASC archive contains it.

    Thin wrapper over ``get_game_data_reader().read_file(casc_path)`` -
    exists so loader code can state intent ("I'm reading a game-data
    file; the Iron Rule applies") at a glance without needing a
    separate import of :class:`CASCReader`.
    """
    return get_game_data_reader().read_file(casc_path)


def read_game_data_rows(casc_path: str, *, encoding: str = "utf-8-sig") -> list[dict[str, str]]:
    """Return a game-data file parsed as tab-delimited rows.

    Reads the file via :func:`read_game_data_bytes` (Iron Rule:
    Reimagined mod first, CASC fallback), decodes it with the given
    encoding (``utf-8-sig`` by default to transparently strip a BOM if
    present - matches most existing loader conventions in the toolkit),
    and yields :class:`csv.DictReader` rows as dicts.

    Returns an empty list when the file is missing from both sources;
    callers that require the file are expected to detect that via
    ``len(rows) == 0`` and decide whether to warn, raise, or continue.
    """
    raw = read_game_data_bytes(casc_path)
    if raw is None:
        return []
    text = raw.decode(encoding, errors="replace")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def list_game_data_files(pattern: str) -> list[str]:
    """List game-data paths matching an ``fnmatch`` pattern, merging
    the mod install's on-disk files with the CASC archive listing.

    The CASC archive's path index covers only CASC-native files; any
    file Reimagined adds that does not exist in vanilla D2R would be
    invisible to :meth:`CASCReader.list_files` alone. This helper
    walks the mod disk in parallel and unions both sources, so every
    file reachable through the Iron Rule's two inputs appears in the
    result.

    The result is sorted and de-duplicated. Example::

        # All ``strings/*.json`` visible to the game, mod wins on
        # overlapping names when the caller later ``read_file()``s them.
        paths = list_game_data_files("data:data/local/lng/strings/*.json")
    """
    reader = get_game_data_reader()
    paths: set[str] = set(reader.list_files(pattern))

    # Parse the CASC pattern into a filesystem-relative pattern and a
    # directory prefix so we can enumerate mod disk additions that CASC
    # never knew about.
    if ":" in pattern:
        prefix, rel_pattern = pattern.split(":", 1)
        prefix = f"{prefix}:"
    else:
        prefix = ""
        rel_pattern = pattern

    if reader.mod_dir is not None:
        # Split rel_pattern into "directory glob + filename glob". The
        # existing usages only glob at the leaf level (``strings/*.json``)
        # so we keep it simple: everything up to the last slash is the
        # literal directory, everything after is the filename glob.
        if "/" in rel_pattern:
            dir_part, file_glob = rel_pattern.rsplit("/", 1)
        else:
            dir_part, file_glob = "", rel_pattern
        mod_dir_path = reader.mod_dir / Path(dir_part.replace("/", "\\"))
        if mod_dir_path.is_dir():
            for entry in mod_dir_path.glob(file_glob):
                if entry.is_file():
                    rel = entry.relative_to(reader.mod_dir).as_posix()
                    paths.add(f"{prefix}{rel}")

    return sorted(paths)

