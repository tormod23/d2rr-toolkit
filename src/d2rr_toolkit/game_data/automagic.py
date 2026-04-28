"""
Loader for automagic.txt - automatic item modifiers (automods).

Items with an ``auto prefix`` value in weapons.txt/armor.txt/misc.txt
get automatic modifiers from this table.  The game stores a 1-based
row index (11 bits) in the item binary which points into this file.

GoMule reference: ``D2TxtFile.AUTOMAGIC.getRow(class_data - 1)``
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.meta import cached_load


logger = logging.getLogger(__name__)

# Automod codes that are Reimagined-internal mechanics and should
# NOT appear in the item tooltip display.
HIDDEN_AUTOMOD_CODES: set[str] = {
    "oskill_hide",  # "Hidden Charm Passive" - internal engine skill
    "charm-property",  # Charm weight tracking - internal mechanic
}


@dataclass(slots=True)
class AutomodEntry:
    """One mod slot from an automagic.txt row (up to 3 per row)."""

    code: str  # property code (e.g. "skilltab", "dmg-undead")
    param: str  # optional param (e.g. "0" for skill tab index)
    value_min: int
    value_max: int

    @property
    def is_fixed(self) -> bool:
        """True if the rolled value is deterministic (min == max)."""
        return self.value_min == self.value_max


@dataclass(slots=True)
class AutomodDefinition:
    """One row from automagic.txt."""

    name: str
    entries: list[AutomodEntry] = field(default_factory=list)


class AutomagicDatabase:
    """Maps 1-based automod IDs to their mod definitions from automagic.txt."""

    def __init__(self) -> None:
        self._rows: list[AutomodDefinition] = []
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load automagic.txt from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("automagic.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except (OSError, KeyError) as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self.load_from_rows(rows, source=str(path))

    def load_from_rows(self, rows: list[dict[str, str]], *, source: str = "<rows>") -> None:
        """Populate the database from pre-parsed rows (Iron Rule entry point)."""
        parsed: list[AutomodDefinition] = []
        for row in rows:
            name = row.get("Name", "").strip()
            if not name:
                continue
            entries: list[AutomodEntry] = []
            for i in range(1, 4):  # mod1..mod3
                code = row.get(f"mod{i}code", "").strip()
                if not code:
                    continue
                param = row.get(f"mod{i}param", "").strip()
                try:
                    vmin = int(row.get(f"mod{i}min", "0").strip() or "0")
                    vmax = int(row.get(f"mod{i}max", "0").strip() or "0")
                except ValueError:
                    vmin = vmax = 0
                entries.append(
                    AutomodEntry(
                        code=code,
                        param=param,
                        value_min=vmin,
                        value_max=vmax,
                    )
                )
            parsed.append(AutomodDefinition(name=name, entries=entries))
        self._rows = parsed
        self._loaded = True
        logger.info("AutomagicDatabase: %d rows loaded from %s", len(self._rows), source)

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get(self, automod_id: int) -> AutomodDefinition | None:
        """Look up by 1-based automod_id from binary. Returns None if out of range."""
        idx = automod_id - 1
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    def display_entries(self, automod_id: int) -> list[AutomodEntry]:
        """Return non-hidden entries for an automod_id (for tooltip display)."""
        defn = self.get(automod_id)
        if defn is None:
            return []
        return [e for e in defn.entries if e.code not in HIDDEN_AUTOMOD_CODES]


# ── Singleton ──────────────────────────────────────────────────────────────

_AUTOMAGIC_DB = AutomagicDatabase()


def get_automagic_db() -> AutomagicDatabase:
    """Return the global AutomagicDatabase singleton."""
    return _AUTOMAGIC_DB


SCHEMA_VERSION_AUTOMAGIC: int = 1


def load_automagic(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`AutomagicDatabase` from ``data/global/excel/automagic.txt``.

    Automagic rules define the implicit modifier ranges that the
    game rolls onto quality-gated base items (e.g. the
    Superior / Low-Quality groups).  The CLI / GUI consults
    this DB whenever it needs to render an affix's
    theoretical min-max range.

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` (or the top-level
    ``GAME_DATA_CACHE.md`` reference) for the invalidation
    contract.  Callers that omit the kwargs get the pre-cache
    behaviour unchanged, just faster on the second launch.

    Args:
        use_cache: ``False`` disables the persistent cache for
            this call only (also honoured via
            ``D2RR_DISABLE_GAME_DATA_CACHE=1``).  Tests use this
            to force a fresh parse without mutating global state.
        source_versions: Optional :class:`SourceVersions`.  When
            omitted the helper resolves it from the current
            :class:`GamePaths` and memoises the result process-
            wide, so a batch of loaders that all default still
            only pays one disk probe.
        cache_dir: Optional cache root override.  Tests route
            this into a ``tmp_path`` fixture; production callers
            rely on the platformdirs default
            (``%LOCALAPPDATA%/d2rr-toolkit/data_cache`` on Windows).
    """

    def _build() -> None:
        """Populate the :class:`AutomagicDatabase` via the Iron Rule."""

        casc_path = "data:data/global/excel/automagic.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.warning("automagic.txt not found in mod or CASC")
            return
        get_automagic_db().load_from_rows(rows, source=casc_path)

    cached_load(
        name="automagic",
        schema_version=SCHEMA_VERSION_AUTOMAGIC,
        singleton=get_automagic_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )
