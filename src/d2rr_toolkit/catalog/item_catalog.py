"""Enumeration/catalog layer over the Reimagined Excel item data.

The GUI's filter feature has two dropdowns:
  1. **Select Item Type** - ~70 filterable categories (Body Armor,
     Sorceress Orb, Any Weapon, Crafted Sunder Charm, ...).
  2. **Select Equipment** - all base items that match the chosen
     category, each with its tier suffix ("Archon Plate [E]").

Both lists come entirely from four game-data files:

  * ``data/global/excel/itemtypes.txt`` - type codes + display labels +
    Equiv1/Equiv2 parent edges + Magic/Rare rollability flags.
  * ``data/global/excel/armor.txt``, ``weapons.txt``, ``misc.txt`` -
    base items with their primary/secondary type codes plus normcode/
    ubercode/ultracode for Normal/Exceptional/Elite tier resolution.

Iron Rule - File access
-----------------------
Every file is read through :func:`get_game_data_reader` /
:meth:`CASCReader.read_file`, which implements the two-source rule
enforced throughout the toolkit:

  1. Reimagined Mod install (disk) - the only authoritative truth.
  2. D2R Resurrected CASC archive - used only when the file is NOT
     present in the mod install.

Both sources share the identical relative path
(``data/global/excel/<name>.txt``), so one CASC-style string addresses
both. No ``excel_base`` arithmetic, no virtual base directory, no
pre-extracted caches. See ``project_data_source_iron_rule.md`` in
memory for the full rationale.

Base-item display names come from :class:`ItemNamesDatabase`, which is
populated separately during game-data load; tier suffixes are
delegated to :func:`get_tier_suffix`. Neither touches files.

Curation of the type list is data-driven too: a category is
considered "filterable" when at least one base item in its equiv
closure has ``Magic=1`` **or** ``Rare=1`` on its own type row in
itemtypes.txt. This automatically excludes potions, gems, runes,
quest items, gold, etc. without any explicit allow/deny list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions

from d2rr_toolkit.adapters.casc import (
    CASCReader,
    get_game_data_reader,
)
from d2rr_toolkit.game_data.item_names import get_item_names_db
from d2rr_toolkit.game_data.item_types import get_item_type_db

logger = logging.getLogger(__name__)

# CASC-style paths for the four files the catalog consumes. These are
# the SAME strings whether the file is served from the mod disk or
# from CASC - see the Iron Rule in the module docstring above.
_CASC_ITEMTYPES = "data:data/global/excel/itemtypes.txt"
_CASC_ARMOR = "data:data/global/excel/armor.txt"
_CASC_WEAPONS = "data:data/global/excel/weapons.txt"
_CASC_MISC = "data:data/global/excel/misc.txt"


def _read_rows_or_raise(reader: CASCReader, casc_path: str) -> list[dict[str, str]]:
    """Read tab-delimited rows, raising FileNotFoundError if empty.

    The shared :func:`read_game_data_rows` returns ``[]`` silently when
    the file is missing, which matches the needs of "optional" loaders.
    The catalog, however, treats each of its four files as mandatory -
    an empty result would yield a degenerate catalog and mask a real
    configuration error. This thin wrapper enforces that distinction.
    """
    raw = reader.read_file(casc_path)
    if raw is None:
        raise FileNotFoundError(
            f"Game data file {casc_path!r} not found in the Reimagined "
            f"mod install and not found in the D2R Resurrected CASC "
            f"archive. Check CASCReader mod_dir / game_dir configuration."
        )
    # Reuse the shared parser by falling back on the bytes we just pulled
    # out of the reader - cheaper than a second lookup.
    import csv
    import io

    text = raw.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


# ── Public data types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ItemTypeEntry:
    """One filterable item category.

    Attributes:
        code:         itemtypes.txt Code (e.g. ``"tors"``, ``"armo"``,
                      ``"csch"``) - stable machine identifier.
        display_name: itemtypes.txt ItemType column (e.g. ``"Armor"``,
                      ``"Any Armor"``, ``"Crafted Sunder Charm"``).
                      Returned verbatim; callers that want different
                      wording are expected to apply presentation-layer
                      aliases themselves.
        equiv_chain:  Transitive closure of Equiv1/Equiv2 parent codes.
                      Always contains ``code`` as the first element and
                      is ordered from self -> root. Empty ``""`` codes
                      are filtered out.
        is_rollable:  ``True`` when itemtypes.txt has ``Magic=1`` or
                      ``Rare=1`` directly on this row. This is the
                      literal per-row flag - honest to the data,
                      useful for diagnostics.
        is_filterable: ``True`` when the bucket behind this category
                      contains at least one base item whose **own**
                      type is rollable. This is the flag the GUI
                      dropdown should filter on. Example: ``bowq``
                      has ``Magic=0, Rare=0`` itself but hosts the
                      rollable descendant ``mboq`` (Magic Bow Quiv),
                      so ``is_filterable`` is ``True`` even though
                      ``is_rollable`` is ``False``.
        item_count:   Number of base items that map into this category
                      (directly or via the equiv chain).
    """

    code: str
    display_name: str
    equiv_chain: tuple[str, ...]
    is_rollable: bool
    is_filterable: bool
    item_count: int


@dataclass(frozen=True)
class ItemEntry:
    """One concrete base item available in the game.

    Attributes:
        code:         3- or 4-character item code (e.g. ``"aar"``,
                      ``"xap"``, ``"cm3"``).
        display_name: Localised base item name from the strings DB
                      (e.g. ``"Ancient Armor"``, ``"Grand Charm"``).
        tier_suffix:  ``" [N]"``, ``" [X]"``, ``" [E]"`` for normal /
                      exceptional / elite armor and weapons. Empty
                      for misc items and anything whose category does
                      not use tiers.
        type_code:    Primary type column of the item row (maps to an
                      ``itemtypes.txt`` Code).
        type2_code:   Secondary type column, or ``None`` when absent.
    """

    code: str
    display_name: str
    tier_suffix: str
    type_code: str
    type2_code: str | None


# ── Implementation ───────────────────────────────────────────────────────────


class ItemCatalog:
    """Query surface for the Item Type / Equipment filter dropdowns.

    Build the catalog once via :meth:`load` after the other game-data
    databases have been loaded, then call :meth:`list_equippable_types`
    and :meth:`list_items_of_type` as needed. Lookups are O(1) for
    single entries and O(k) for the filtered lists where k is the
    number of matching items.
    """

    def __init__(self) -> None:
        self._types: dict[str, ItemTypeEntry] = {}
        self._items: dict[str, ItemEntry] = {}
        # item code -> set of type codes in its equiv chain (incl. own types).
        # Enables O(1) "does this item belong to type X?" lookup.
        self._item_to_type_set: dict[str, frozenset[str]] = {}
        self._loaded = False

    # ── Loading ────────────────────────────────────────────────────────────

    def load(self, casc_reader: CASCReader | None = None) -> None:
        """Build the catalog from the game data via a :class:`CASCReader`.

        Reads four files - ``itemtypes.txt``, ``armor.txt``,
        ``weapons.txt``, ``misc.txt`` - each addressed by a single
        CASC-style path (e.g. ``data:data/global/excel/itemtypes.txt``).
        The reader honours the Iron Rule on every access: Reimagined
        mod install first, D2R Resurrected CASC archive only as
        fallback. See the module docstring.

        Args:
            casc_reader: Optional explicit reader. When ``None`` the
                process-wide singleton from
                :func:`get_game_data_reader` is used - which is the
                right choice for nearly every caller.

        Raises:
            FileNotFoundError: When any of the four files is absent
                from both the mod install and the CASC archive. A
                silent empty load would leave :attr:`is_loaded`
                pointing at a degenerate catalog and mask the real
                configuration problem.
        """
        self._types.clear()
        self._items.clear()
        self._item_to_type_set.clear()
        self._loaded = False

        reader = casc_reader if casc_reader is not None else get_game_data_reader()

        itemtypes_rows = _read_rows_or_raise(reader, _CASC_ITEMTYPES)
        armor_rows = _read_rows_or_raise(reader, _CASC_ARMOR)
        weapon_rows = _read_rows_or_raise(reader, _CASC_WEAPONS)
        misc_rows = _read_rows_or_raise(reader, _CASC_MISC)

        self._build_type_registry(itemtypes_rows)
        self._build_item_registry(armor_rows, weapon_rows, misc_rows)
        self._populate_item_counts()

        # Fail loud on a parse-level empty result. Individual files
        # may be sparse but zero types + zero items together means the
        # four reads produced unusable content - usually a sign that
        # the reader's mod_dir / game_dir are misconfigured.
        if not self._types or not self._items:
            raise FileNotFoundError(
                "ItemCatalog.load: parsed zero types or zero items "
                f"(types={len(self._types)}, items={len(self._items)}). "
                "Check CASCReader mod_dir and game_dir - files were "
                "returned but appear empty or malformed."
            )

        self._loaded = True
        logger.info(
            "ItemCatalog loaded: %d types, %d base items (mod_dir=%s)",
            len(self._types),
            len(self._items),
            reader.mod_dir,
        )

    # ── Type registry ──────────────────────────────────────────────────────

    def _build_type_registry(self, rows: list[dict[str, str]]) -> None:
        """Extract every itemtypes.txt row as an :class:`ItemTypeEntry`.

        Equiv chains are resolved in a second pass after all rows are
        known so forward references work regardless of file order.
        """
        raw: dict[str, tuple[str, str, str, bool]] = {}
        for row in rows:
            code = row.get("Code", "").strip()
            if not code or code == "Expansion":
                continue
            label = row.get("ItemType", "").strip()
            equiv1 = row.get("Equiv1", "").strip()
            equiv2 = row.get("Equiv2", "").strip()
            rollable = row.get("Magic", "").strip() == "1" or row.get("Rare", "").strip() == "1"
            raw[code] = (label or code, equiv1, equiv2, rollable)

        # Resolve transitive closure: for each type, walk Equiv1/2 upward
        # until we hit codes with no further parents. Guard against cycles
        # by capping traversal depth - the real data is acyclic but we
        # prefer a defensive cap over trust.
        def _chain(start: str) -> tuple[str, ...]:
            seen = [start]
            frontier = [start]
            while frontier:
                nxt: list[str] = []
                for c in frontier:
                    entry = raw.get(c)
                    if not entry:
                        continue
                    _label, e1, e2, _rollable = entry
                    for parent in (e1, e2):
                        if parent and parent not in seen:
                            seen.append(parent)
                            nxt.append(parent)
                frontier = nxt
                if len(seen) > 64:  # safety net
                    logger.warning(
                        "ItemCatalog: equiv chain from %r exceeded 64 entries - truncating.",
                        start,
                    )
                    break
            return tuple(seen)

        for code, (label, _e1, _e2, rollable) in raw.items():
            self._types[code] = ItemTypeEntry(
                code=code,
                display_name=label,
                equiv_chain=_chain(code),
                is_rollable=rollable,
                is_filterable=False,  # filled in by _populate_item_counts
                item_count=0,  # filled in by _populate_item_counts
            )

    # ── Item registry ──────────────────────────────────────────────────────

    def _build_item_registry(
        self,
        armor_rows: list[dict[str, str]],
        weapon_rows: list[dict[str, str]],
        misc_rows: list[dict[str, str]],
    ) -> None:
        """Register every base item across armor/weapons/misc.

        For each row we resolve:
          * primary type code (``type`` column)
          * secondary type code (``type2`` column, often empty)
          * display name via :class:`ItemNamesDatabase`
          * tier suffix via :func:`get_tier_suffix` on the live
            :class:`ItemTypeDatabase` singleton.
        """
        from d2rr_toolkit.display.item_display import get_tier_suffix

        type_db = get_item_type_db()
        names_db = get_item_names_db()

        def _add(rows: Iterable[dict[str, str]]) -> None:
            for row in rows:
                code = row.get("code", "").strip().lower()
                tcol = row.get("type", "").strip()
                tcol2 = row.get("type2", "").strip() or None
                if not code or not tcol:
                    continue
                # Display name: prefer localised lookup, fall back to the
                # raw ``name`` column when the strings DB has nothing.
                display_name = (
                    (names_db.get_base_item_name(code) if names_db.is_loaded() else None)
                    or row.get("name", "").strip()
                    or code
                )
                tier = get_tier_suffix(code, type_db)
                self._items[code] = ItemEntry(
                    code=code,
                    display_name=display_name,
                    tier_suffix=tier,
                    type_code=tcol,
                    type2_code=tcol2,
                )

        _add(armor_rows)
        _add(weapon_rows)
        _add(misc_rows)

        # For each item, precompute the full set of type codes it
        # belongs to (its own type_code + type2_code + every ancestor
        # in each of their equiv chains). This enables O(1) "belongs
        # to X" checks during list_items_of_type.
        for item in self._items.values():
            bucket: set[str] = set()
            for t in (item.type_code, item.type2_code):
                if not t:
                    continue
                entry = self._types.get(t)
                if entry is None:
                    # Item references a type that itemtypes.txt does not
                    # declare - keep the self-reference so a direct
                    # lookup still works, even though no ancestors are
                    # known.
                    bucket.add(t)
                else:
                    bucket.update(entry.equiv_chain)
            self._item_to_type_set[item.code] = frozenset(bucket)

    def _populate_item_counts(self) -> None:
        """Count items per type bucket and derive ``is_filterable``.

        Two passes over the item-to-type mapping:
          1. ``item_count``   - how many base items route into this bucket.
          2. ``is_filterable`` - whether any of those items has a rollable
             **own** type. An item's "own type" is ``type_code`` or
             ``type2_code``; a type is rollable if its Magic/Rare flag
             is set. The bucket's ``is_filterable`` is the OR of all
             its members' rollability.
        """
        counts: dict[str, int] = {code: 0 for code in self._types}
        filterable: dict[str, bool] = {code: False for code in self._types}

        rollable_type_codes = {c for c, e in self._types.items() if e.is_rollable}

        for item in self._items.values():
            item_is_rollable = item.type_code in rollable_type_codes or (
                item.type2_code in rollable_type_codes if item.type2_code else False
            )
            for t in self._item_to_type_set.get(item.code, frozenset()):
                if t in counts:
                    counts[t] += 1
                    if item_is_rollable:
                        filterable[t] = True

        for code, count in counts.items():
            entry = self._types[code]
            self._types[code] = ItemTypeEntry(
                code=entry.code,
                display_name=entry.display_name,
                equiv_chain=entry.equiv_chain,
                is_rollable=entry.is_rollable,
                is_filterable=filterable[code],
                item_count=count,
            )

    # ── Public query API ───────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def list_equippable_types(self) -> list[ItemTypeEntry]:
        """Return every category that contains at least one rollable
        base item (directly or via its equiv descendants).

        An item is considered rollable when its own primary or
        secondary type is flagged ``Magic=1`` or ``Rare=1`` in
        itemtypes.txt. A bucket is filterable when at least one item
        in its equiv closure meets that bar. This inclusion of
        descendants matters in Reimagined: categories like ``bowq``
        (Bow Quiver) are not rollable themselves, but they host
        ``mboq`` (Magic Bow Quiv) items that are - so the GUI needs
        the Quiver bucket to surface so users can find unique Magic
        Arrows through it.

        Empty buckets (``item_count == 0``) are skipped - they would
        lead to a dropdown entry that resolves to an empty Equipment
        list.

        Alphabetically sorted by ``display_name`` (case-insensitive).
        """
        result = [
            entry for entry in self._types.values() if entry.is_filterable and entry.item_count > 0
        ]
        result.sort(key=lambda e: e.display_name.lower())
        return result

    def iter_types(self) -> list[ItemTypeEntry]:
        """Return every :class:`ItemTypeEntry` known to the catalog.

        Useful for consumers that want to apply their own filter rule
        (e.g. "include any category with at least one item, regardless
        of rollability"). The list is stable, sorted alphabetically by
        ``display_name``.
        """
        return sorted(self._types.values(), key=lambda e: e.display_name.lower())

    def list_items_of_type(
        self,
        type_code: str,
        *,
        include_descendants: bool = True,
    ) -> list[ItemEntry]:
        """Return every base item that belongs to ``type_code``.

        Args:
            type_code: Itemtypes.txt Code to filter on. Case-sensitive
                to match the raw column values.
            include_descendants: When ``True`` (default) any item whose
                type chain reaches ``type_code`` via Equiv1/Equiv2
                qualifies - so ``"armo"`` returns all armour across
                body / helm / shield / gloves / boots / belt. When
                ``False`` only items whose primary or secondary type
                is literally ``type_code`` qualify.

        The returned list is sorted alphabetically by ``display_name``
        (case-insensitive); tier suffixes are included in the returned
        string but are not part of the sort key, so ``Ancient Armor [N]``
        comes before ``Archon Plate [E]`` regardless of tier.
        """
        if include_descendants:
            matches = [
                item
                for item in self._items.values()
                if type_code in self._item_to_type_set.get(item.code, frozenset())
            ]
        else:
            matches = [
                item
                for item in self._items.values()
                if item.type_code == type_code or item.type2_code == type_code
            ]
        matches.sort(key=lambda e: e.display_name.lower())
        return matches

    def get_item_type(self, type_code: str) -> ItemTypeEntry | None:
        """Return the :class:`ItemTypeEntry` for ``item_code``, or None if unknown."""

        return self._types.get(type_code)

    def get_item(self, item_code: str) -> ItemEntry | None:
        """Return the :class:`CatalogEntry` for ``key``, or None if unknown."""

        return self._items.get(item_code.lower())


# ── Singleton glue ───────────────────────────────────────────────────────────

_catalog: ItemCatalog | None = None


def get_item_catalog() -> ItemCatalog:
    """Return the process-wide :class:`ItemCatalog` instance.

    Creates an empty catalog on first access. Call
    :func:`load_item_catalog` once after game data is loaded to
    populate it. Callers that query an unloaded catalog get empty
    lists - no crashes, so GUI startup flow stays simple.
    """
    global _catalog
    if _catalog is None:
        _catalog = ItemCatalog()
    return _catalog


SCHEMA_VERSION_ITEM_CATALOG: int = 1


def load_item_catalog(
    casc_reader: CASCReader | None = None,
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`ItemCatalog` from the game data.

    Produces the two dropdown-ready lists the GUI item filter
    needs: every filterable item type (~70 categories) and every
    base item that rolls into each type.  Built from four source
    files already loaded by the other game-data loaders
    (``itemtypes.txt``, ``armor.txt``, ``weapons.txt``,
    ``misc.txt``); see :class:`ItemCatalog.load` for the wiring.

    When ``casc_reader`` is omitted the shared
    :func:`get_game_data_reader` singleton is used, which is the
    right choice for nearly every caller (CLI, GUI).  Explicit
    readers are accepted mainly so tests can inject a
    :class:`CASCReader` configured against a fixture game install.

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` (or the top-level
    ``GAME_DATA_CACHE.md`` reference) for the invalidation
    contract.  Callers that omit the cache kwargs get the pre-
    cache behaviour unchanged, just faster on the second launch.

    Args:
        casc_reader: Optional explicit :class:`CASCReader` (mainly
            for tests).
        use_cache: ``False`` disables the persistent cache for
            this call only (also honoured via
            ``D2RR_DISABLE_GAME_DATA_CACHE=1``).
        source_versions: Optional :class:`SourceVersions`; shared
            instance preferred across batched loaders.
        cache_dir: Optional cache root override (tests route this
            into a ``tmp_path``).
    """
    from d2rr_toolkit.meta import cached_load

    def _build() -> None:
        get_item_catalog().load(casc_reader)

    cached_load(
        name="item_catalog",
        schema_version=SCHEMA_VERSION_ITEM_CATALOG,
        singleton=get_item_catalog(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


