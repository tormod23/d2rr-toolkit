"""
Loads and provides access to skills.txt data.

Used to resolve skill IDs to human-readable names in Encode 2/3 item
properties (skill-on-event and charged-skill modifiers).

Skill ID = row index in skills.txt (0-based, after header row).
The '*Id' column mirrors the row index and is used for validation.

Data source priority: excel/reimagined/ first (mod overrides vanilla).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """Definition of one skill from skills.txt."""

    skill_id: int
    name: str  # 'skill' column - internal identifier, NOT the
    # player-facing display name (e.g. "Levitate").
    charclass: str  # 'charclass' column - empty string for class-less skills
    # skilldesc.txt lookup key from skills.txt ``skilldesc`` column.
    # Joins with skilldesc.txt to find the ``str name`` key that
    # StringsDatabase resolves to the game's actual tooltip label
    # (e.g. "LevitateName" -> "Levitation Mastery").
    skilldesc: str = ""


class SkillDatabase:
    """In-memory database of skill definitions from skills.txt."""

    def __init__(self) -> None:
        self._skills: dict[int, SkillDefinition] = {}
        # skilldesc row key -> ``str name`` column value.  Populated by
        # :meth:`load_skilldesc_rows` so :meth:`display_name` can turn
        # a skill id into the tooltip label via the string table.
        self._skilldesc_to_str_name: dict[str, str] = {}
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load skill definitions from a tab-delimited skills.txt on disk.

        Kept for direct-path callers (tests, debug tools). The module-level
        :func:`load_skills` goes through the Iron Rule via
        :func:`load_from_rows` and is the preferred entry point in
        production code.
        """
        if not path.exists():
            logger.warning("skills.txt not found at %s", path)
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except OSError as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self.load_from_rows(rows, source=str(path))

    def load_from_rows(self, rows: list[dict[str, str]], *, source: str = "<rows>") -> None:
        """Populate the database from pre-parsed tab-delimited rows.

        Skill ID is determined by row position (0-based after header),
        not by the '*Id' column (which mirrors the index but is unreliable
        in some mod versions).
        """
        for skill_id, row in enumerate(rows):
            name = (row.get("skill") or "").strip()
            charclass = (row.get("charclass") or "").strip()
            skilldesc = (row.get("skilldesc") or "").strip()
            if not name:
                continue
            self._skills[skill_id] = SkillDefinition(
                skill_id=skill_id,
                name=name,
                charclass=charclass,
                skilldesc=skilldesc,
            )
        self._loaded = True
        logger.info("Skills: %d entries loaded from %s", len(self._skills), source)

    def load_skilldesc_rows(
        self,
        rows: list[dict[str, str]],
        *,
        source: str = "<rows>",
    ) -> None:
        """Populate the skilldesc -> str_name mapping from skilldesc.txt.

        ``skilldesc.txt`` joins on the ``skilldesc`` column of
        skills.txt and supplies the string-table key (``str name``)
        the game looks up for the skill's display label.
        """
        self._skilldesc_to_str_name.clear()
        for row in rows:
            key = (row.get("skilldesc") or "").strip()
            str_name = (row.get("str name") or "").strip()
            if key and str_name:
                self._skilldesc_to_str_name[key] = str_name
        logger.info(
            "Skills: %d skilldesc str-name mappings loaded from %s",
            len(self._skilldesc_to_str_name),
            source,
        )

    def display_name(
        self,
        skill_id: int,
        *,
        strings_db: "object | None" = None,
        lang: str = "enUS",
    ) -> str | None:
        """Return the player-facing skill label for ``skill_id``.

        Looks up the skill's ``skilldesc`` column, joins against
        skilldesc.txt for the ``str name`` key, then resolves that
        key via ``strings_db`` to the localized display text
        (e.g. ``383`` -> ``"Levitate"`` in skills.txt -> ``"levitate"``
        in skilldesc.txt -> ``"LevitateName"`` in strings DB ->
        ``"Levitation Mastery"`` final label).

        Falls back to the internal ``skill`` column from skills.txt
        when the string table doesn't carry the key or ``strings_db``
        is missing.
        """
        defn = self._skills.get(skill_id)
        if defn is None:
            return None
        if strings_db is not None and defn.skilldesc:
            str_key = self._skilldesc_to_str_name.get(defn.skilldesc)
            if str_key:
                try:
                    label = strings_db.get(str_key, lang)
                except (KeyError, AttributeError) as exc:
                    logger.warning(
                        "strings_db.get failed for key=%r lang=%r: %s",
                        str_key,
                        lang,
                        exc,
                    )
                    label = None
                if label:
                    return label
        return defn.name

    def get(self, skill_id: int) -> SkillDefinition | None:
        """Return the SkillDefinition for a given ID, or None if unknown."""
        return self._skills.get(skill_id)

    def name(self, skill_id: int) -> str | None:
        """Return the skill's display name - player-facing label from
        the string table when available, falling back to the internal
        ``skill`` column from skills.txt.

        This is what the property formatter substitutes into
        tooltips like ``"+2 to %s"`` (stat 107 item_singleskill) and
        ``"15% Chance to cast level X %s on striking"`` (encode=2
        skill-on-event stats), so the GUI matches the in-game text
        exactly - e.g. skill 383 becomes "Levitation Mastery" not
        the internal "Levitate".
        """
        defn = self._skills.get(skill_id)
        if defn is None:
            return None
        # Try string-table resolution first; fall back to skill name.
        if defn.skilldesc:
            try:
                from d2rr_toolkit.game_data.item_names import get_item_names_db

                strings = get_item_names_db()._strings
                str_key = self._skilldesc_to_str_name.get(defn.skilldesc)
                if str_key:
                    label = strings.get(str_key)
                    if label:
                        return label
            except (ImportError, AttributeError, KeyError) as exc:
                logger.warning(
                    "skills.name string lookup fallback for id=%s: %s",
                    skill_id,
                    exc,
                )
        return defn.name

    def id_by_name(self, skill_name: str) -> int | None:
        """Return the skill ID for a given name (case-insensitive), or None."""
        target = skill_name.lower().strip()
        for sid, defn in self._skills.items():
            if defn.name and defn.name.lower() == target:
                return sid
        return None

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def __len__(self) -> int:
        return len(self._skills)


_SKILL_DB = SkillDatabase()


def get_skill_db() -> SkillDatabase:
    """Return the module-level :class:`SkillDatabase` singleton."""
    return _SKILL_DB


SCHEMA_VERSION_SKILLS: int = 2  # +skilldesc str_name mapping


def load_skills(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`SkillDatabase` from ``data/global/excel/skills.txt``.

    Skill definitions - ``skill_id`` (row index) -> ``name`` +
    ``charclass``.  Used throughout the property formatter to
    render skill names on chance-to-cast / charged / oskill
    stats (encode=2 / encode=3 ISC entries).  Reimagined ships
    ~490 rows; the hidden charm-passive skill 449 lives here too
    and is filtered out at the formatter layer (see
    ``HIDDEN_SKILL_PARAMS`` in ``property_formatter.py``).

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` (or the top-level
    ``GAME_DATA_CACHE.md`` reference) for the invalidation
    contract.

    Args:
        use_cache: ``False`` disables the persistent cache for
            this call only (also honoured via
            ``D2RR_DISABLE_GAME_DATA_CACHE=1``).
        source_versions: Optional :class:`SourceVersions`.  When
            omitted the helper resolves it from the current
            :class:`GamePaths` and memoises the result.
        cache_dir: Optional cache root override (tests route this
            into a ``tmp_path``).
    """
    from d2rr_toolkit.meta import cached_load

    def _build() -> None:
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        rows = read_game_data_rows("data:data/global/excel/skills.txt")
        if not rows:
            logger.warning("skills.txt not found in mod or CASC - skill names will be unavailable.")
            return
        get_skill_db().load_from_rows(
            rows,
            source="data:data/global/excel/skills.txt",
        )
        # skilldesc.txt - optional.  When absent we still return the
        # internal skill names (backwards-compatible with vanilla);
        # when present the ``name()`` / ``display_name()`` paths can
        # hand back the localized tooltip label via the string table
        # (e.g. "Levitate" -> "Levitation Mastery").
        sd_rows = read_game_data_rows("data:data/global/excel/skilldesc.txt")
        if sd_rows:
            get_skill_db().load_skilldesc_rows(
                sd_rows,
                source="data:data/global/excel/skilldesc.txt",
            )

    cached_load(
        name="skills",
        schema_version=SCHEMA_VERSION_SKILLS,
        singleton=get_skill_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )

