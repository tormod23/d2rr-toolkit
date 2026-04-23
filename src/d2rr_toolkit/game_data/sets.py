"""
Loads sets.txt and setitems.txt - complete set bonus definitions.

Two types of set bonuses:
  1. Per-item partial bonuses (aprop1-5 in setitems.txt):
     Active when bonus_mask bit is set in the binary. Already parsed into
     set_bonus_properties by the d2s_parser. These are item-specific.

  2. Set-wide bonuses (PCode2-5 and FCode1-8 in sets.txt):
     Apply to ALL members of a set when enough pieces are equipped.
     NOT stored in the binary - loaded from sets.txt for display only.

For the inspect display, both types are shown per item:
  - Per-item (aprop): "X-piece bonus: +25 Defense"
  - Set-wide (PCode/FCode): "2 Items: +10% Life Stolen per Hit"
  - Full set (FCode): "Full Set: +100 Defense"

[SOURCE: excel/reimagined/sets.txt + setitems.txt - always read at runtime]
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.game_data.item_stat_cost import ItemStatCostDatabase
    from d2rr_toolkit.game_data.properties import PropertiesDatabase
    from d2rr_toolkit.game_data.property_formatter import PropertyFormatter
    from d2rr_toolkit.game_data.skills import SkillDatabase
    from d2rr_toolkit.meta.source_versions import SourceVersions

logger = logging.getLogger(__name__)


@dataclass
class SetBonusEntry:
    """One property entry in a set bonus tier."""

    code: str  # property code (e.g. "res-fire", "str")
    param: str  # optional param (e.g. skill ID as string)
    value_min: int
    value_max: int

    def effective_value(self) -> int:
        """Return the single effective value (min=max for most set bonuses)."""
        return self.value_min  # min and max are usually identical for set bonuses

    def format(
        self,
        formatter: "PropertyFormatter",
        props_db: "PropertiesDatabase",
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
    ) -> str | None:
        """Format this bonus entry to a display string.

        ``setitems.txt`` / ``sets.txt`` encode chance-to-cast and charged
        skills in two columns per entry: the ``min`` column carries the
        chance (or charge count) and the ``max`` column carries the
        skill level.  The generic
        :meth:`PropertyFormatter.format_code_value` pathway only passes
        a single value through ``_apply_stat_template``, which hard-
        codes the secondary ``%d`` placeholder to ``0`` - that produces
        the "chance to cast level **0** ..." display reported against
        Darkmage's Solar Flair.  For encode=2 (skill-on-event) and
        encode=3 (charged) stats we therefore assemble a proper prop
        dict with explicit ``chance`` / ``level`` / ``skill_id`` keys
        and route through :meth:`format_prop`, which understands that
        schema.  Every other code (single-value stats like ``str``,
        ``res-all``, damage percentages, ...) continues through the
        existing single-value code path unchanged.
        """
        prop_def = props_db.get(self.code)
        if prop_def is not None:
            stat_id = prop_def.primary_stat_id(isc_db)
            stat_def = isc_db.get(stat_id) if stat_id is not None else None
            if stat_def is not None and stat_def.encode in (2, 3):
                return self._format_encoded_skill(
                    stat_id,
                    stat_def.encode,
                    formatter,
                    isc_db,
                    skills_db,
                    lang,
                )

        return formatter.format_code_value(
            self.code,
            self.effective_value(),
            self.param,
            props_db,
            isc_db,
            skills_db,
            lang,
        )

    def _format_encoded_skill(
        self,
        stat_id: int,
        encode: int,
        formatter: "PropertyFormatter",
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None",
        lang: str,
    ) -> str | None:
        """Build an encode=2/3 prop dict from this entry and format it.

        setitems.txt / sets.txt use string skill names (``"Shock Wave"``)
        in the param column; the property formatter's encode=2 path
        expects an integer ``skill_id``.  When a skills database is
        available we resolve the name; otherwise we leave the id at 0
        and let the formatter fall back to the skill name string.
        """
        skill_id = 0
        skill_name: str | None = None
        if self.param:
            # Accept a numeric skill id (rare but legal) without touching skills_db.
            try:
                skill_id = int(self.param)
            except ValueError:
                skill_name = self.param
                if skills_db is not None:
                    skill_id = skills_db.id_by_name(self.param) or 0
        if not skill_name and skills_db is not None and skill_id:
            skill_name = skills_db.name(skill_id)

        if encode == 2:
            # min = chance, max = skill level (per setitems.txt/sets.txt
            # convention mirrored by properties.txt's Min / Max hint
            # columns: "% Chance" / "Skill Level").
            prop = {
                "stat_id": stat_id,
                "name": "",
                "chance": self.value_min,
                "level": self.value_max,
                "skill_id": skill_id,
                "skill_name": skill_name,
            }
        else:
            # encode == 3 - charged skill.  Reimagined does not currently
            # use ``charged`` in any tier bonus, but the same min/max
            # ambiguity would apply: max is the skill level, min would
            # be the charge count.  Mirror the convention defensively so
            # a future use case doesn't silently regress.
            prop = {
                "stat_id": stat_id,
                "name": "",
                "level": self.value_max,
                "skill_id": skill_id,
                "skill_name": skill_name,
                "charges": self.value_min,
                "max_charges": self.value_min,
            }
        return formatter.format_prop(prop, isc_db, skills_db=skills_db, lang=lang)


@dataclass
class SetTierBonus:
    """A set bonus tier: the bonus(es) active when N pieces are equipped."""

    pieces_required: int  # 2, 3, 4, 5 for partial; 0 for full set
    is_full_set: bool = False
    entries: list[SetBonusEntry] = field(default_factory=list)


@dataclass
class SetDefinition:
    """Complete definition of one set from sets.txt."""

    name: str  # internal name = display name (sets.txt `name` col)
    partial_tiers: list[SetTierBonus] = field(default_factory=list)  # 2/3/4/5-piece set-wide
    full_tier: SetTierBonus | None = None  # full set bonuses (all pieces)
    member_names: list[str] = field(default_factory=list)  # set item display names

    def total_pieces(self) -> int:
        """Number of pieces in the set (derived from member count)."""
        return len(self.member_names)


@dataclass
class SetItemTierBonus:
    """Per-item bonus active when N pieces of the set are equipped."""

    pieces_required: int  # 2, 3, 4, 5, 6
    entries: list[SetBonusEntry] = field(default_factory=list)


@dataclass
class SetItemDefinition:
    """Definition of one set item from setitems.txt."""

    row_index: int  # 0-based row index (= set_item_id from binary)
    name: str  # display name key (= setitems.txt `index` column)
    set_name: str  # which set this belongs to (= `set` column -> links to sets.txt)
    item_code: str  # base item code (= `item` column)
    level_req: int = 0  # required level from setitems.txt `lvl req` column
    invtransform: str = ""  # inventory sprite color transform code (e.g. "bwht", "cgrn")
    invfile: str = ""  # inventory sprite filename override
    tier_bonuses: list[SetItemTierBonus] = field(default_factory=list)
    # Note: item-own props (prop1-9) are in the binary magical_properties; not stored here.


def _parse_p_entries(row: dict, tier: int) -> list[SetBonusEntry]:
    """Parse partial set bonus entries from sets.txt for a given tier (2-5)."""
    entries = []
    for slot in ("a", "b"):
        code = row.get(f"PCode{tier}{slot}", "").strip()
        if not code:
            continue
        param = row.get(f"PParam{tier}{slot}", "").strip()
        try:
            vmin = int(row.get(f"PMin{tier}{slot}", "0").strip() or "0")
            vmax = int(row.get(f"PMax{tier}{slot}", "0").strip() or "0")
        except ValueError:
            vmin = vmax = 0
        entries.append(SetBonusEntry(code=code, param=param, value_min=vmin, value_max=vmax))
    return entries


def _parse_f_entries(row: dict) -> list[SetBonusEntry]:
    """Parse full set bonus entries from sets.txt (FCode1..FCode8)."""
    entries = []
    for i in range(1, 9):
        code = row.get(f"FCode{i}", "").strip()
        if not code:
            continue
        param = row.get(f"FParam{i}", "").strip()
        try:
            vmin = int(row.get(f"FMin{i}", "0").strip() or "0")
            vmax = int(row.get(f"FMax{i}", "0").strip() or "0")
        except ValueError:
            vmin = vmax = 0
        entries.append(SetBonusEntry(code=code, param=param, value_min=vmin, value_max=vmax))
    return entries


def _parse_aprop_entries(row: dict, tier: int) -> list[SetBonusEntry]:
    """Parse per-item set bonus entries from setitems.txt for a given tier (1-5).

    Tier 1 -> 2 pieces required (aprop1a/1b)
    Tier 2 -> 3 pieces required (aprop2a/2b)
    ...
    Tier 5 -> 6 pieces required (aprop5a/5b)
    """
    entries = []
    for slot in ("a", "b"):
        code = row.get(f"aprop{tier}{slot}", "").strip()
        if not code:
            continue
        param = row.get(f"apar{tier}{slot}", "").strip()
        try:
            vmin = int(row.get(f"amin{tier}{slot}", "0").strip() or "0")
            vmax = int(row.get(f"amax{tier}{slot}", "0").strip() or "0")
        except ValueError:
            vmin = vmax = 0
        entries.append(SetBonusEntry(code=code, param=param, value_min=vmin, value_max=vmax))
    return entries


class SetsDatabase:
    """Complete set bonus information from sets.txt and setitems.txt."""

    def __init__(self) -> None:
        self._sets: dict[str, SetDefinition] = {}  # name -> SetDefinition
        self._set_items_by_id: dict[int, SetItemDefinition] = {}  # *ID -> definition
        self._set_items_by_name: dict[str, SetItemDefinition] = {}
        self._loaded = False

    def load(self, base: Path) -> None:
        """Load sets.txt + setitems.txt from a disk directory (backward-compat)."""
        sets_path = base / "sets.txt"
        setitems_path = base / "setitems.txt"

        if not sets_path.exists():
            logger.warning("sets.txt not found at %s", sets_path)
            return

        try:
            with open(sets_path, encoding="utf-8", errors="replace") as f:
                sets_rows = list(csv.DictReader(f, delimiter="\t"))
        except OSError as e:
            logger.error("Cannot read %s: %s", sets_path, e)
            return

        setitems_rows: list[dict[str, str]] = []
        if setitems_path.exists():
            try:
                with open(setitems_path, encoding="utf-8", errors="replace") as f:
                    setitems_rows = list(csv.DictReader(f, delimiter="\t"))
            except OSError as e:
                logger.error("Cannot read %s: %s", setitems_path, e)

        self.load_from_rows(sets_rows, setitems_rows, source=str(base))

    def load_from_rows(
        self,
        sets_rows: list[dict[str, str]],
        setitems_rows: list[dict[str, str]],
        *,
        source: str = "<rows>",
    ) -> None:
        """Populate the database from pre-parsed rows (Iron Rule entry point)."""
        for row in sets_rows:
            name = row.get("name", "").strip()
            if not name:
                continue

            partial_tiers = []
            for tier in range(2, 6):  # 2, 3, 4, 5
                entries = _parse_p_entries(row, tier)
                if entries:
                    partial_tiers.append(
                        SetTierBonus(
                            pieces_required=tier,
                            is_full_set=False,
                            entries=entries,
                        )
                    )

            full_entries = _parse_f_entries(row)
            full_tier = (
                SetTierBonus(
                    pieces_required=0,
                    is_full_set=True,
                    entries=full_entries,
                )
                if full_entries
                else None
            )

            self._sets[name] = SetDefinition(
                name=name,
                partial_tiers=partial_tiers,
                full_tier=full_tier,
            )

        for row in setitems_rows:
            item_name = row.get("index", "").strip()
            set_name = row.get("set", "").strip()
            item_code = row.get("item", "").strip()
            star_id = row.get("*ID", "").strip()
            if not item_name or not star_id.isdigit():
                continue
            star_id_int = int(star_id)

            # Per-item tier bonuses (aprop1-5)
            tier_bonuses = []
            for aprop_tier in range(1, 6):  # 1-5 -> 2-6 pieces
                entries = _parse_aprop_entries(row, aprop_tier)
                if entries:
                    tier_bonuses.append(
                        SetItemTierBonus(
                            pieces_required=aprop_tier + 1,  # tier 1 = 2 pieces
                            entries=entries,
                        )
                    )

            try:
                _lvl_req = int(row.get("lvl req", "0").strip() or "0")
            except ValueError:
                _lvl_req = 0
            item_def = SetItemDefinition(
                row_index=star_id_int,
                name=item_name,
                set_name=set_name,
                item_code=item_code,
                level_req=_lvl_req,
                invtransform=row.get("invtransform", "").strip(),
                invfile=row.get("invfile", "").strip(),
                tier_bonuses=tier_bonuses,
            )
            self._set_items_by_id[star_id_int] = item_def
            self._set_items_by_name[item_name] = item_def

            # Register this item as a member of its set
            set_def = self._sets.get(set_name)
            if set_def is not None and item_name not in set_def.member_names:
                set_def.member_names.append(item_name)

        self._loaded = True
        logger.info(
            "SetsDatabase: %d sets, %d set items loaded from %s",
            len(self._sets),
            len(self._set_items_by_id),
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get_set(self, name: str) -> SetDefinition | None:
        """Get set definition by internal name."""
        return self._sets.get(name)

    def get_set_item(self, set_item_id: int) -> SetItemDefinition | None:
        """Get set item definition by *ID from setitems.txt."""
        return self._set_items_by_id.get(set_item_id)

    def get_set_item_by_name(self, name: str) -> SetItemDefinition | None:
        """Get set item definition by display name."""
        return self._set_items_by_name.get(name)

    def get_set_for_item(self, row_index: int) -> tuple[SetDefinition, SetItemDefinition] | None:
        """Get (SetDefinition, SetItemDefinition) for a given set_item_id."""
        item_def = self.get_set_item(row_index)
        if item_def is None:
            return None
        set_def = self._sets.get(item_def.set_name)
        if set_def is None:
            return None
        return set_def, item_def

    def __len__(self) -> int:
        return len(self._sets)


_SETS_DB = SetsDatabase()


def get_sets_db() -> SetsDatabase:
    """Return the global SetsDatabase singleton."""
    return _SETS_DB


SCHEMA_VERSION_SETS: int = 1


def load_sets(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`SetsDatabase` from the set-item tables.

    Reads ``data/global/excel/sets.txt`` (set-wide PCode / FCode
    bonuses) and ``data/global/excel/setitems.txt`` (per-item
    aprop tier bonuses).  Consumed by the property formatter's
    :class:`SetBonusEntry` pipeline for tooltip rendering,
    including the CTC chance-to-cast encoding where the ``min``
    column carries the chance and ``max`` carries the skill
    level (see ``FORMATTED_PROPERTIES.md`` §"Chance-to-cast Set
    Bonuses").

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` for the invalidation contract.

    Args:
        use_cache: ``False`` disables the cache for this call.
        source_versions: Optional :class:`SourceVersions`; shared
            instance preferred across batched loaders.
        cache_dir: Optional cache root override.
    """
    from d2rr_toolkit.meta import cached_load

    def _build() -> None:
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        sets_rows = read_game_data_rows("data:data/global/excel/sets.txt")
        setitems_rows = read_game_data_rows("data:data/global/excel/setitems.txt")
        if not sets_rows:
            logger.warning("sets.txt not found in mod or CASC - set bonuses cannot be resolved.")
            return
        get_sets_db().load_from_rows(
            sets_rows,
            setitems_rows,
            source="data:data/global/excel/{sets,setitems}.txt (Iron Rule)",
        )

    cached_load(
        name="sets",
        schema_version=SCHEMA_VERSION_SETS,
        singleton=get_sets_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


