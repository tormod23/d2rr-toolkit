"""Single source of truth for "has the input data changed?".

Every persistent cache in the pipeline - the toolkit's game-data
cache (see :mod:`d2rr_toolkit.meta.cache`) and downstream consumers
like the D2RR ToolkitGUI's ``SQLiteAssetCache`` - uses
:class:`SourceVersions` as the *only* invalidation key.  This module
is the sole place that knows how to extract those version markers
from disk; everyone else consumes the resulting frozen dataclass.

Reader-facing documentation for the cache this feeds lives in
``src/d2rr_toolkit/GAME_DATA_CACHE.md`` (end-to-end reference,
loader wiring, benchmark table).  This file is the implementation
reference for the markers themselves.

Two reasons this lives in the toolkit instead of each cache rolling
its own:

1. **Correctness.** Two independent parsers of ``.build.info`` /
   ``modinfo.json`` are two independent bugs waiting to happen. One
   function -> one answer -> every cache agrees on what "fresh"
   means, by construction.
2. **Co-location.** The toolkit already owns ``GamePaths`` and
   ``CASCReader``; reading two more small files from the same
   install is a natural extension of that responsibility.

The version markers themselves are:

* ``game_version`` - a short SHA-256 prefix of the full
  ``<game_dir>/.build.info`` bytes.  That file is Blizzard's
  launcher manifest (Branch!STRING, Active!DEC, Build Key!HEX,
  Version!STRING, ...); its hash changes on every game patch
  regardless of which internal column Blizzard bumped.  Using the
  hash instead of a parsed column future-proofs us against column
  layout changes and deliberately avoids coupling to Blizzard's
  private format.
* ``mod_version`` - the literal ``version`` field from
  ``<mod_dir>/<name>.mpq/modinfo.json``.  Mod version is under the
  mod author's control; trusting the declared string is exactly
  what mod versioning exists for.  ``None`` when no mod is active.
* ``mod_name`` - informational only.  Not part of the cache key
  (renaming a mod without changing its content must not force a
  rebuild).

A missing / malformed ``modinfo.json`` degrades to
``mod_version=None`` with a warning; a missing ``.build.info``
raises :class:`SourceVersionsError` because we cannot safely cache
against an unknown game state.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# Short hash prefix for the game_version token. 16 hex chars = 64 bits of
# collision resistance, which is overkill for a cache-invalidation key but
# keeps log lines compact while still being unambiguous.
_BUILD_INFO_HASH_LENGTH = 16


class SourceVersionsError(RuntimeError):
    """Raised when the authoritative game version cannot be determined.

    The toolkit refuses to produce a cache key without a stable
    game-version anchor - a wrong positive here means every future
    cache lookup could serve stale data.  Only raised for ``.build.info``;
    modinfo.json errors degrade to ``mod_version=None``.
    """


@dataclass(frozen=True, slots=True)
class SourceVersions:
    """Versions of the on-disk inputs every cache depends on.

    Equality and hashing are structural, so two instances compare
    equal iff **both** the game build and the active mod version
    match.  That tuple is exactly the invalidation key every cache
    needs, nothing more.

    Attributes:
        game_version:
            Opaque token derived from the bytes of
            ``<game_dir>/.build.info``.  Changes whenever Blizzard
            ships a patch.  Never empty for a valid install.
        mod_version:
            The ``version`` field from
            ``<mod_dir>/<name>.mpq/modinfo.json``, or ``None`` for a
            vanilla run / missing / malformed JSON.
        mod_name:
            The ``name`` field from the same JSON, or ``None``.
            Informational - deliberately **not** part of equality
            semantics so a mod rename without content change does
            not trigger a pipeline-wide cache invalidation.
    """

    game_version: str
    mod_version: str | None
    mod_name: str | None = None

    # ``mod_name`` intentionally excluded from the equality key by
    # overriding __eq__ and __hash__.  The frozen dataclass would
    # otherwise compare all three fields.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceVersions):
            return NotImplemented
        return self.game_version == other.game_version and self.mod_version == other.mod_version

    def __hash__(self) -> int:
        return hash((self.game_version, self.mod_version))

    def cache_key(self) -> str:
        """Human-readable single-line key for diagnostics + logs."""
        if self.mod_version:
            mod = f"{self.mod_name or '<anon>'}@{self.mod_version}"
        else:
            mod = "<vanilla>"
        return f"game={self.game_version} mod={mod}"


# ── Internal file readers ────────────────────────────────────────────────────


def _hash_build_info(path: Path) -> str:
    """Hash the bytes of ``.build.info`` to a short hex string.

    Reading + hashing the whole file is deliberately opaque: we do not
    depend on Blizzard's column layout (they have added columns in
    past patches), only on the fact that a patch changes the file.
    """
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise SourceVersionsError(f".build.info missing or unreadable at {path}: {e}") from e
    if not raw:
        raise SourceVersionsError(f".build.info is empty at {path}")
    return hashlib.sha256(raw).hexdigest()[:_BUILD_INFO_HASH_LENGTH]


def _read_modinfo(path: Path) -> tuple[str | None, str | None]:
    """Return ``(version, name)`` from modinfo.json, both may be None.

    Missing / malformed JSON degrades to ``(None, None)`` with a
    warning: callers can still cache against a "no mod" key, which
    is the correct behaviour for a vanilla run and keeps the tool
    usable against a broken mod install.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return (None, None)
    except OSError as e:
        logger.warning("modinfo.json unreadable at %s: %s", path, e)
        return (None, None)

    try:
        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except (ValueError, UnicodeDecodeError) as e:
        logger.warning("modinfo.json malformed at %s: %s", path, e)
        return (None, None)

    if not isinstance(data, dict):
        logger.warning("modinfo.json top-level is not an object at %s", path)
        return (None, None)

    version = data.get("version")
    name = data.get("name")
    version_str = str(version).strip() if version else None
    name_str = str(name).strip() if name else None
    # Empty strings normalise to None so equality never mistakes an
    # absent field for a present-but-empty one.
    return (version_str or None, name_str or None)


def _candidate_modinfo_paths(mod_dir: Path) -> list[Path]:
    """Return the candidate locations where ``modinfo.json`` may live.

    Reimagined and friends ship it at ``<mod_dir>/<name>.mpq/modinfo.json``
    but the directory name is the mod author's choice.  We accept either:

      * ``<mod_dir>/modinfo.json`` (mod_dir points straight at the mpq)
      * ``<mod_dir>/*.mpq/modinfo.json`` (mod_dir points at the parent)

    The first existing file wins - deterministic but permissive,
    matching the way ``CASCReader`` itself discovers the mod tree.
    """
    direct = mod_dir / "modinfo.json"
    candidates = [direct]
    if mod_dir.is_dir():
        for child in sorted(mod_dir.iterdir()):
            if child.is_dir() and child.suffix.lower() == ".mpq":
                candidates.append(child / "modinfo.json")
    return candidates


# ── Public entry point ───────────────────────────────────────────────────────


def get_source_versions(
    *,
    game_dir: Path,
    mod_dir: Path | None = None,
) -> SourceVersions:
    """Read the two authoritative version markers from disk.

    Args:
        game_dir: The D2R install root (the directory that contains
            ``.build.info`` and ``Data/``).  Usually
            ``GamePaths.d2r_install``.
        mod_dir: Optional active mod directory.  May point either at
            ``<install>/mods/Reimagined`` (parent) or straight at the
            ``Reimagined.mpq`` MPQ directory - both layouts resolve
            correctly.  ``None`` means "vanilla D2R, no mod active".

    Returns:
        A :class:`SourceVersions` with the game hash resolved and
        the mod version either resolved or ``None``.

    Raises:
        SourceVersionsError: when ``.build.info`` is missing,
            unreadable, or empty.  Callers cannot safely cache
            against an unknown game state, so this is fatal.
    """
    game_version = _hash_build_info(game_dir / ".build.info")

    mod_version: str | None = None
    mod_name: str | None = None
    if mod_dir is not None:
        for candidate in _candidate_modinfo_paths(mod_dir):
            if candidate.is_file():
                mod_version, mod_name = _read_modinfo(candidate)
                break

    return SourceVersions(
        game_version=game_version,
        mod_version=mod_version,
        mod_name=mod_name,
    )
