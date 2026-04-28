"""
Loads item type classification from game data files.

Determines whether an item code belongs to Armor.txt, Weapons.txt,
or Misc.txt - which controls which type-specific fields are present
in the binary item data.

Data source priority: excel/reimagined/ first, then excel/original/
(Reimagined mod may add or modify item entries).

This is the MINIMUM game data needed for correct item parsing:
  - Armor items:  have defense + durability fields
  - Weapon items: have durability fields (no defense), plus damage [SPEC_ONLY]
  - Misc items:   may have stackable quantity, no defense/durability

Without this classification, the parser cannot correctly determine
which fields to read after the extended item header, causing
all subsequent items in the list to be misaligned.
"""

import csv
import logging
from enum import Enum, auto
from pathlib import Path
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.meta import cached_load

logger = logging.getLogger(__name__)


class ItemCategory(Enum):
    """Item category determining which type-specific fields are present."""

    ARMOR = auto()  # In Armor.txt - has defense + durability
    WEAPON = auto()  # In Weapons.txt - has durability (no defense) + damage fields [SPEC_ONLY]
    MISC = auto()  # In Misc.txt - varies (stackable qty, no defense/durability typically)
    UNKNOWN = auto()  # Not found in any loaded file


class ItemTypeDatabase:
    """In-memory database of item codes to their categories.

    Built from the game data .txt files at startup.
    All item codes are lowercase for consistent lookup.
    """

    def __init__(self) -> None:
        self._armor_codes: set[str] = set()
        self._weapon_codes: set[str] = set()
        self._misc_codes: set[str] = set()
        self._quantity_codes: set[str] = set()  # items with 9-bit quantity in simple format
        self._auto_prefix_codes: set[str] = set()  # items with class-specific auto prefix
        self._bitfield1_codes: set[str] = set()  # items with bitfield1 > 0
        self._shield_codes: set[str] = set()  # armor items that are shields (type='shie')
        self._stackable_codes: set[str] = set()  # misc items with stackable=1
        self._max_stack: dict[str, int] = {}  # item code -> maxstack from misc.txt
        self._tome_codes: set[str] = set()  # misc items with type='book' (tomes)
        self._throwing_weapon_codes: set[str] = set()  # weapons with stackable=1 (throwing)
        # Tier lookup: item_code -> "normal" | "exceptional" | "elite"
        # Built from normcode/ubercode/ultracode columns in armor.txt and weapons.txt.
        self._tier_lookup: dict[str, str] = {}
        # Base item requirements: item_code -> (reqstr, reqdex, levelreq)
        self._requirements: dict[str, tuple[int, int, int]] = {}
        # Weapon stats: item_code -> (mindam, maxdam, min2h, max2h, speed)
        self._weapon_stats: dict[str, tuple[int, int, int, int, int]] = {}
        # Shield block chance: item_code -> base block % (from armor.txt `block` col)
        self._block_chance: dict[str, int] = {}
        # Item type code: item_code -> type column value (e.g. "rune", "gema", "ques")
        self._item_type: dict[str, str] = {}
        # Inventory dimensions: item_code -> (invwidth, invheight)
        self._inv_dimensions: dict[str, tuple[int, int]] = {}
        # Inventory sprite filename: item_code -> invfile value (for sprite lookup)
        self._inv_file: dict[str, str] = {}
        # InvTrans colormap ID: item_code -> int (0=none, 1..8=colormap file).
        # Used by d2rr_toolkit.display.tinted_sprite for palette-based tinting.
        # 0 is the default (no tinting), so only non-zero values are stored.
        self._inv_trans: dict[str, int] = {}
        # Belt rows: item_code -> belt column value (number of extra slot rows)
        self._belt_rows: dict[str, int] = {}
        # Base durability: item_code -> durability from armor.txt/weapons.txt
        self._base_durability: dict[str, int] = {}
        # itemtypes.txt: type_code -> class restriction code (e.g. "ama", "bar", "sor")
        # None/empty = equippable by all classes
        self._type_to_class: dict[str, str] = {}
        # itemtypes.txt: type_code -> human-readable label (e.g. "Belt", "Body Armor")
        self._type_to_label: dict[str, str] = {}
        # itemtypes.txt: type_code -> BodyLoc1 (e.g. "head", "tors", "rarm")
        self._type_to_bodyloc: dict[str, str] = {}
        # itemtypes.txt: type_code -> tuple of its Equiv1/Equiv2 parent codes
        # (non-empty only). Used by the catalog layer to walk the type
        # hierarchy for filter queries ("Any Armor" ⊇ Body Armor ⊇ ...).
        self._type_equiv: dict[str, tuple[str, ...]] = {}
        # itemtypes.txt: set of type_codes that are rollable as magic or
        # rare (Magic==1 OR Rare==1). This is the canonical flag that
        # distinguishes equippable/wearable categories from materials,
        # potions, quest items etc. in the GUI's filter dropdown.
        self._type_rollable: set[str] = set()
        # Base item -> secondary type column (armor/weapons/misc `type2`).
        # Many items leave this empty; we only store non-empty entries.
        self._item_type2: dict[str, str] = {}
        self._loaded = False

    @staticmethod
    def _load_file_rows(path: Path) -> list[dict[str, str]]:
        """Read a tab-delimited game data file once and return all rows as dicts.

        Returns an empty list if the file does not exist or cannot be read.
        """
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter="\t")
                return list(reader)
        except OSError as e:
            logger.error("Failed to read %s: %s", path, e)
            return []

    @staticmethod
    def _safe_int(value: str) -> int:
        """Parse a string as int, returning 0 for empty or invalid values."""
        v = value.strip()
        try:
            return int(v) if v else 0
        except ValueError:
            return 0

    def _process_armor_rows(self, rows: list[dict[str, str]]) -> None:
        """Extract all needed data from armor.txt rows in a single pass."""
        for row in rows:
            code = row.get("code", "").strip().lower()
            if not code or code == "expansion":
                continue

            # Category
            self._armor_codes.add(code)

            # Auto prefix
            ap = row.get("auto prefix", "").strip()
            if ap and ap != "0":
                self._auto_prefix_codes.add(code)

            # [BINARY_VERIFIED TC12/TC13/TC14] bitfield1
            bf1 = row.get("bitfield1", "").strip()
            if bf1 and bf1 != "0":
                self._bitfield1_codes.add(code)

            # [BINARY_VERIFIED TC32] Shield detection
            itype = row.get("type", "").strip().lower()
            if itype == "shie":
                self._shield_codes.add(code)

            # Item type column
            t = row.get("type", "").strip()
            if t:
                self._item_type[code] = t
            t2 = row.get("type2", "").strip()
            if t2:
                self._item_type2[code] = t2

            # Tier codes from normcode/ubercode/ultracode
            norm = row.get("normcode", "").strip().lower()
            uber = row.get("ubercode", "").strip().lower()
            ultra = row.get("ultracode", "").strip().lower()
            if norm:
                self._tier_lookup[norm] = "normal"
            if uber:
                self._tier_lookup[uber] = "exceptional"
            if ultra:
                self._tier_lookup[ultra] = "elite"

            # Requirements
            self._requirements[code] = (
                self._safe_int(row.get("reqstr", "")),
                self._safe_int(row.get("reqdex", "")),
                self._safe_int(row.get("levelreq", "")),
            )

            # Block chance (shields)
            block = row.get("block", "").strip()
            if block:
                try:
                    self._block_chance[code] = int(block)
                except ValueError:
                    pass

            # Inventory dimensions
            try:
                w = int(row.get("invwidth", "1").strip() or "1")
                h = int(row.get("invheight", "1").strip() or "1")
            except ValueError:
                w, h = 1, 1
            self._inv_dimensions[code] = (w, h)

            # Inventory sprite
            invfile = row.get("invfile", "").strip()
            if invfile:
                self._inv_file[code] = invfile

            # InvTrans colormap ID (0=none, 1..8=colormap file)
            self._store_inv_trans(code, row)

            # Base durability
            dur = self._safe_int(row.get("durability", ""))
            if dur > 0:
                self._base_durability[code] = dur

            # Belt row count (belts only)
            belt_val = self._safe_int(row.get("belt", ""))
            if belt_val > 0:
                self._belt_rows[code] = belt_val

    def _store_inv_trans(self, code: str, row: dict[str, str]) -> None:
        """Parse the InvTrans column from a row and store if non-zero.

        InvTrans is a small integer 0..8 that selects a colormap file
        under data/global/items/palette/ for palette-based tinting.
        Only non-zero values are stored; the default is 0 ("no tint").
        """
        val = self._safe_int(row.get("InvTrans", ""))
        if val:
            self._inv_trans[code] = val

    def _process_weapon_rows(self, rows: list[dict[str, str]]) -> None:
        """Extract all needed data from weapons.txt rows in a single pass."""
        for row in rows:
            code = row.get("code", "").strip().lower()
            if not code or code == "expansion":
                continue

            # Category
            self._weapon_codes.add(code)

            # Auto prefix
            ap = row.get("auto prefix", "").strip()
            if ap and ap != "0":
                self._auto_prefix_codes.add(code)

            # [BINARY_VERIFIED TC12/TC13/TC14] bitfield1
            bf1 = row.get("bitfield1", "").strip()
            if bf1 and bf1 != "0":
                self._bitfield1_codes.add(code)

            # Throwing weapons (stackable=1 in weapons.txt)
            stack_val = row.get("stackable", "").strip()
            if stack_val == "1":
                self._throwing_weapon_codes.add(code)

            # Item type column
            t = row.get("type", "").strip()
            if t:
                self._item_type[code] = t
            t2 = row.get("type2", "").strip()
            if t2:
                self._item_type2[code] = t2

            # Tier codes from normcode/ubercode/ultracode
            norm = row.get("normcode", "").strip().lower()
            uber = row.get("ubercode", "").strip().lower()
            ultra = row.get("ultracode", "").strip().lower()
            if norm:
                self._tier_lookup[norm] = "normal"
            if uber:
                self._tier_lookup[uber] = "exceptional"
            if ultra:
                self._tier_lookup[ultra] = "elite"

            # Requirements
            self._requirements[code] = (
                self._safe_int(row.get("reqstr", "")),
                self._safe_int(row.get("reqdex", "")),
                self._safe_int(row.get("levelreq", "")),
            )

            # Weapon stats
            self._weapon_stats[code] = (
                self._safe_int(row.get("mindam", "")),
                self._safe_int(row.get("maxdam", "")),
                self._safe_int(row.get("2handmindam", "")),
                self._safe_int(row.get("2handmaxdam", "")),
                self._safe_int(row.get("speed", "")),
            )

            # Inventory dimensions
            try:
                w = int(row.get("invwidth", "1").strip() or "1")
                h = int(row.get("invheight", "1").strip() or "1")
            except ValueError:
                w, h = 1, 1
            self._inv_dimensions[code] = (w, h)

            # Inventory sprite
            invfile = row.get("invfile", "").strip()
            if invfile:
                self._inv_file[code] = invfile

            # InvTrans colormap ID (0=none, 1..8=colormap file)
            self._store_inv_trans(code, row)

            # Base durability
            dur = self._safe_int(row.get("durability", ""))
            if dur > 0:
                self._base_durability[code] = dur

    def _process_misc_rows(self, rows: list[dict[str, str]]) -> None:
        """Extract all needed data from misc.txt rows in a single pass."""
        for row in rows:
            code = row.get("code", "").strip().lower()
            if not code or code == "expansion":
                continue

            # Category
            self._misc_codes.add(code)

            # Auto prefix
            ap = row.get("auto prefix", "").strip()
            if ap and ap != "0":
                self._auto_prefix_codes.add(code)

            # [BINARY_VERIFIED TC12/TC13/TC14] bitfield1
            bf1 = row.get("bitfield1", "").strip()
            if bf1 and bf1 != "0":
                self._bitfield1_codes.add(code)

            # [BINARY_VERIFIED TC07/TC11/TC03] Quantity codes
            ass_val = row.get("AdvancedStashStackable", "").strip()
            if ass_val == "1":
                self._quantity_codes.add(code)

            # [BINARY_VERIFIED TC29] Stackable and tome codes
            stack_val = row.get("stackable", "").strip()
            if stack_val == "1":
                self._stackable_codes.add(code)
                try:
                    ms = int(row.get("maxstack", "0").strip() or "0")
                    if ms > 0:
                        self._max_stack[code] = ms
                except ValueError:
                    pass

            type_val = row.get("type", "").strip()
            if type_val.lower() == "book":
                self._tome_codes.add(code)

            # Item type column
            if type_val:
                self._item_type[code] = type_val
            t2 = row.get("type2", "").strip()
            if t2:
                self._item_type2[code] = t2

            # Requirements
            self._requirements[code] = (
                self._safe_int(row.get("reqstr", "")),
                self._safe_int(row.get("reqdex", "")),
                self._safe_int(row.get("levelreq", "")),
            )

            # Inventory dimensions
            try:
                w = int(row.get("invwidth", "1").strip() or "1")
                h = int(row.get("invheight", "1").strip() or "1")
            except ValueError:
                w, h = 1, 1
            self._inv_dimensions[code] = (w, h)

            # Inventory sprite
            invfile = row.get("invfile", "").strip()
            if invfile:
                self._inv_file[code] = invfile

            # InvTrans colormap ID (0=none, 1..8=colormap file)
            self._store_inv_trans(code, row)

    def _process_itemtypes_rows(self, rows: list[dict[str, str]]) -> None:
        """Extract class restrictions, labels, equiv chain, and rollable
        flags from itemtypes.txt rows.
        """
        for row in rows:
            code = row.get("Code", "").strip()
            if not code or code == "Expansion":
                continue
            label = row.get("ItemType", "").strip()
            cls = row.get("Class", "").strip()
            bodyloc = row.get("BodyLoc1", "").strip()
            if label:
                self._type_to_label[code] = label
            if cls:
                self._type_to_class[code] = cls
            if bodyloc:
                self._type_to_bodyloc[code] = bodyloc
            equivs = tuple(
                e
                for e in (
                    row.get("Equiv1", "").strip(),
                    row.get("Equiv2", "").strip(),
                )
                if e
            )
            if equivs:
                self._type_equiv[code] = equivs
            # Magic/Rare flags decide whether this type shows up in the
            # GUI's "Select Item Type" filter. Potions, gems, runes,
            # quest items etc. leave both columns blank (-> 0).
            if row.get("Magic", "").strip() == "1" or row.get("Rare", "").strip() == "1":
                self._type_rollable.add(code)
        logger.info(
            "Loaded %d item types from itemtypes.txt (%d with class restrictions, %d rollable)",
            len(self._type_to_label),
            len(self._type_to_class),
            len(self._type_rollable),
        )

    def load(self, excel_dir: Path) -> None:
        """Load item codes from a disk directory (backward-compat)."""
        armor_rows = self._load_file_rows(excel_dir / "armor.txt")
        weapon_rows = self._load_file_rows(excel_dir / "weapons.txt")
        misc_rows = self._load_file_rows(excel_dir / "misc.txt")
        itemtypes_rows = self._load_file_rows(excel_dir / "itemtypes.txt")
        self.load_from_rows(
            armor_rows,
            weapon_rows,
            misc_rows,
            itemtypes_rows,
            source=str(excel_dir),
        )

    def load_from_rows(
        self,
        armor_rows: list[dict[str, str]],
        weapon_rows: list[dict[str, str]],
        misc_rows: list[dict[str, str]],
        itemtypes_rows: list[dict[str, str]],
        *,
        source: str = "<rows>",
    ) -> None:
        """Populate the database from pre-parsed rows (Iron Rule entry point).

        Each of the four row lists is processed in a single pass; all four
        are required for a complete picture of the item tree, but a
        partial set (e.g. only armor + itemtypes) still leaves the
        database in a consistent, queryable state - callers that need
        stricter failure modes should check :attr:`is_loaded` and the
        various code sets after this call.
        """
        self._process_armor_rows(armor_rows)
        self._process_weapon_rows(weapon_rows)
        self._process_misc_rows(misc_rows)
        self._process_itemtypes_rows(itemtypes_rows)
        self._loaded = True
        logger.info(
            "Item type DB: %d armor, %d weapon, %d misc codes loaded from %s",
            len(self._armor_codes),
            len(self._weapon_codes),
            len(self._misc_codes),
            source,
        )

    def classify(self, item_code: str) -> ItemCategory:
        """Classify an item code into its category.

        Args:
            item_code: Huffman-decoded item code (e.g. 'lgl', 'ssd', 'hp1').

        Returns:
            ItemCategory enum value.
        """
        code = item_code.lower().strip()
        if code in self._armor_codes:
            return ItemCategory.ARMOR
        if code in self._weapon_codes:
            return ItemCategory.WEAPON
        if code in self._misc_codes:
            return ItemCategory.MISC
        if not self._loaded:
            logger.warning(
                "ItemTypeDatabase not loaded - cannot classify '%s'. "
                "Call load() with excel/ directory path first.",
                item_code,
            )
        else:
            logger.debug("Item code '%s' not found in any game data file.", item_code)
        return ItemCategory.UNKNOWN

    def is_loaded(self) -> bool:
        """True if game data has been loaded."""
        return self._loaded

    def contains(self, item_code: str) -> bool:
        """Return True if item_code is known (armor, weapon, or misc) - NO warning logged.

        Use this for probe/scan loops that test arbitrary bit sequences as potential
        item codes. Unlike classify(), this never logs warnings for unknown codes.
        """
        code = item_code.lower().strip()
        return code in self._armor_codes or code in self._weapon_codes or code in self._misc_codes

    # ------------------------------------------------------------------ #
    # Introspection helpers used by d2rr_toolkit.catalog.item_catalog    #
    # ------------------------------------------------------------------ #

    def iter_item_codes(self) -> Iterator[str]:
        """Yield every item code known to this database (armor+weap+misc).

        Order is unspecified (implementation detail: sorted). Intended
        for catalog-style enumeration where the caller does its own
        sort/group.
        """
        return iter(sorted(self._armor_codes | self._weapon_codes | self._misc_codes))

    def iter_type_codes(self) -> Iterator[str]:
        """Yield every itemtypes.txt Code known to this database.

        Includes rollable and non-rollable types alike - callers that
        only want the GUI-relevant subset should filter with
        :meth:`is_type_rollable`.
        """
        return iter(sorted(self._type_to_label))

    def get_item_type2(self, item_code: str) -> str:
        """Return the secondary type column of a base item (or empty string).

        Many base items leave the `type2` column blank; this returns
        ``""`` in that case rather than raising, matching the behaviour
        of :meth:`get_item_type`.
        """
        return self._item_type2.get(item_code.lower().strip(), "")

    def get_type_equiv(self, type_code: str) -> tuple[str, ...]:
        """Return the Equiv1/Equiv2 parent codes for a type, in order.

        Empty parents are stripped; a type without any Equiv columns
        returns an empty tuple.
        """
        return self._type_equiv.get(type_code, ())

    def get_itype_ancestors(self, item_code: str) -> set[str]:
        """Return the full ancestor set of itypes for an item.

        Starts from the item's direct ``type`` + ``type2`` columns in
        armor.txt / weapons.txt / misc.txt, then walks the
        ``Equiv1`` / ``Equiv2`` parent chain in itemtypes.txt until no
        new parents are discovered.  Used by the corruption /
        enchantment / stat-breakdown modules to decide which recipe
        buckets apply to a given save-file item (e.g. Large Shield
        ``tow`` -> {``tow``, ``shie``, ``shld``, ``armo``, ``any``}).

        Guarantees termination via the visited set - even if itypes.txt
        contains a cycle, the walk stops the second time a node is
        reached.  Returns an empty set for codes not in any item file.
        """
        code = item_code.lower().strip()
        if not code:
            return set()
        start_types: list[str] = []
        t = self._item_type.get(code, "").strip()
        t2 = self._item_type2.get(code, "").strip()
        if t:
            start_types.append(t)
        if t2 and t2 != t:
            start_types.append(t2)
        if not start_types:
            return set()

        result: set[str] = set(start_types)
        frontier: list[str] = list(start_types)
        while frontier:
            cur = frontier.pop()
            for parent in self._type_equiv.get(cur, ()):
                if parent and parent not in result:
                    result.add(parent)
                    frontier.append(parent)
        return result

    def is_type_rollable(self, type_code: str) -> bool:
        """True when the type has ``Magic==1`` OR ``Rare==1`` in itemtypes.txt.

        This is the canonical discriminator between "equippable /
        wearable / socketable" types (what a GUI filter dropdown wants
        to show) and purely-consumable types (potions, scrolls, quest
        items, gold, etc.).
        """
        return type_code in self._type_rollable

    def get_item_tier(self, item_code: str) -> str:
        """Return the tier of an item code: 'normal', 'exceptional', or 'elite'.

        Determined by normcode/ubercode/ultracode columns in armor.txt and weapons.txt:
          - code == normcode  -> 'normal'
          - code == ubercode  -> 'exceptional'
          - code == ultracode -> 'elite'

        Returns 'normal' if the code is not found in the tier lookup.

        Examples:
          'ltp' (Light Plate, normcode) -> 'normal'
          '7s8' (Thresher, ultracode)   -> 'elite'
          'uhn' (Boneweave, ultracode)  -> 'elite'
        """
        return self._tier_lookup.get(item_code.lower().strip(), "normal")

    def get_weapon_stats(self, item_code: str) -> tuple[int, int, int, int, int]:
        """Return (mindam, maxdam, min2h, max2h, speed) for a weapon code.

        Returns (0, 0, 0, 0, 0) if not a weapon or unknown.
        """
        return self._weapon_stats.get(item_code.lower().strip(), (0, 0, 0, 0, 0))

    def get_requirements(self, item_code: str) -> tuple[int, int, int]:
        """Return (reqstr, reqdex, levelreq) for a base item code.

        Values come from armor.txt / weapons.txt columns reqstr, reqdex, levelreq.
        Returns (0, 0, 0) if the item code is unknown.
        """
        return self._requirements.get(item_code.lower().strip(), (0, 0, 0))

    def get_block_chance(self, item_code: str) -> int:
        """Return base block chance % for a shield, or 0 if not a shield."""
        return self._block_chance.get(item_code.lower().strip(), 0)

    def get_belt_slots(self, item_code: str) -> int:
        """Return extra belt slots beyond the base 4, or 0 if not a belt.

        Belt index -> row count: 1-2 = 2 rows (8 slots, +4), 3-4 = 3 rows
        (12 slots, +8), 5-6 = 4 rows (16 slots, +12).
        """
        belt_idx = self._belt_rows.get(item_code.lower().strip(), 0)
        if belt_idx <= 0:
            return 0
        if belt_idx <= 2:
            return 4
        if belt_idx <= 4:
            return 8
        return 12

    def get_item_type(self, item_code: str) -> str:
        """Return the 'type' column value for an item code (e.g. 'rune', 'gema')."""
        return self._item_type.get(item_code.lower().strip(), "")

    def get_inv_dimensions(self, item_code: str) -> tuple[int, int]:
        """Return (invwidth, invheight) for an item code. Default (1, 1)."""
        return self._inv_dimensions.get(item_code.lower().strip(), (1, 1))

    def get_inv_file(self, item_code: str) -> str:
        """Return the invfile sprite name for an item code, or empty string."""
        return self._inv_file.get(item_code.lower().strip(), "")

    def get_inv_transform_id(self, item_code: str) -> int:
        """Return the palette colormap ID from the ``InvTrans`` column.

        Colormap IDs identify which file under ``data/global/items/palette/``
        the D2 palette-tinting pipeline should use:

            0 = no tinting (even if a color code exists, no transform)
            1 = grey.dat          (in-game, ground)
            2 = grey2.dat         (in-game)
            3 = brown.dat         (in-game)
            4 = gold.dat          (in-game)
            5 = greybrown.dat     (in-game)
            6 = invgrey.dat       (inventory grey)
            7 = invgrey2.dat      (inventory grey alt)
            8 = invgreybrown.dat  (inventory grey-brown)

        Returns:
            Integer 0..8. 0 is the safe default for unknown codes and
            items without a transform - the caller should interpret 0
            as "do not tint this item".
        """
        return self._inv_trans.get(item_code.lower().strip(), 0)

    def get_base_durability(self, item_code: str) -> int:
        """Return base durability from armor/weapons.txt, or 0 if unknown."""
        return self._base_durability.get(item_code.lower().strip(), 0)

    def has_durability_bits(self, item_code: str) -> bool:
        """Return True if weapons.txt/armor.txt has ``durability>0`` for the item.

        Informational helper derived from the same ``_base_durability``
        dict that :meth:`get_base_durability` consults.  Not used by
        the parser - the authoritative in-save sentinel for "no
        durability section follows" is ``max_dur == 0`` at runtime,
        which the parser reads directly and branches on.  This
        helper stays exposed for callers that want a static,
        pre-parse answer ("does this item have durability bits at
        all?") - the only current weapon in Reimagined where this
        returns False is Phase Blade (``7cr``), whose weapons.txt
        row has ``durability=0, nodurability=1``.

        Note that ``nodurability=1`` alone is NOT a reliable predicate:
        every Reimagined bow / crossbow sets ``nodurability=1`` but
        keeps ``durability=250`` and therefore still carries the
        full durability block in the binary.
        """
        return self._base_durability.get(item_code.lower().strip(), 0) > 0

    def get_class_restriction(self, item_code: str) -> str | None:
        """Return the class restriction code for an item, or None if all classes.

        Resolution chain: item_code -> type (armor/weapons/misc.txt) -> Class (itemtypes.txt).
        Returns short codes like 'ama', 'bar', 'sor', 'ass', 'nec', 'pal', 'dru', 'war'.
        """
        item_type = self._item_type.get(item_code.lower().strip(), "")
        if not item_type:
            return None
        return self._type_to_class.get(item_type)

    def get_item_type_label(self, item_code: str) -> str:
        """Return the human-readable item type label (e.g. 'Belt', 'Pelt', 'Orb').

        Resolution: item_code -> type column -> ItemType label from itemtypes.txt.
        """
        item_type = self._item_type.get(item_code.lower().strip(), "")
        if not item_type:
            return ""
        return self._type_to_label.get(item_type, item_type)

    def get_all_type_labels(self) -> dict[str, str]:
        """Return the full type_code -> label mapping from itemtypes.txt."""
        return dict(self._type_to_label)

    def get_type_class_map(self) -> dict[str, str]:
        """Return the type_code -> class restriction mapping."""
        return dict(self._type_to_class)

    def has_bitfield1(self, code: str) -> bool:
        """Return True if item has bitfield1 > 0 in game data.

        [BINARY_VERIFIED TC12/TC13/TC14] bitfield1 controls whether the
        extended header contains gfx_index + has_class fields:
        - bitfield1 > 0 (ring, amu, jewel, armor, weapons): has_gfx flag,
          optional gfx_index(3+1), has_class flag, optional class_data(11).
        - bitfield1 = 0 (charms, pliers, orbs, etc.): only 1 flag bit,
          no gfx data, no has_class field.
        """
        return code.lower() in self._bitfield1_codes

    def has_auto_prefix(self, code: str) -> bool:
        """Return True if an item has class-specific data (auto prefix).

        [BINARY_VERIFIED TC09] Weapons with auto_prefix=312 have 11-bit
        class_data in the extended header. Items without auto prefix
        (armor, misc, jewels) do NOT have class_data even if has_class=1.
        """
        return code.lower() in self._auto_prefix_codes

    def is_shield(self, code: str) -> bool:
        """Return True if the item is a shield (type='shie' in armor.txt).

        [BINARY_VERIFIED TC32] Shields have 2 additional unknown bits after
        the standard 2-bit unknown_post_dur field in the armor data layout.
        Without these 2 extra bits, property parsing starts 2 bits too early,
        causing all subsequent stat IDs to be misread.
        """
        return code.lower() in self._shield_codes

    def is_throwing_weapon(self, code: str) -> bool:
        """Return True if the weapon is a throwing weapon (stackable=1 in weapons.txt).

        Throwing weapons (throwing knives, javelins, battle darts, etc.) use
        Quantity instead of Durability. Their type-specific data is different
        from melee weapons.
        """
        return code.lower() in self._throwing_weapon_codes

    def is_stackable(self, code: str) -> bool:
        """Return True if a misc item has stackable=1 in misc.txt.

        [BINARY_VERIFIED TC29] Extended stackable items (rune stacks, tomes,
        arrows, bolts, quivers) have a raw 9-bit quantity field in the
        type-specific area, separate from ISC-based magical properties.

        This is different from is_quantity_item() which applies to simple items.
        Gem Bags (bag) have stackable=0 and use ISC stat 386 instead.
        """
        return code.lower() in self._stackable_codes

    def is_tome(self, code: str) -> bool:
        """Return True if a misc item is a tome (type='book' in misc.txt).

        [BINARY_VERIFIED TC29] Tomes have a 5-bit prefix (value=16) before
        the 9-bit quantity field. Other stackable items do not have this prefix.
        """
        return code.lower() in self._tome_codes

    def get_max_stack(self, code: str) -> int:
        """Return the maxstack value for a stackable item, or 100 as default."""
        return self._max_stack.get(code.lower(), 100)

    def is_quantity_item(self, code: str) -> bool:
        """Return True if a simple item has a 9-bit quantity field.

        [BINARY_VERIFIED TC07] hp1 (AdvancedStashStackable=empty) has NO quantity, 80 bits.
        [BINARY_VERIFIED TC11] gmd (AdvancedStashStackable=1) has quantity, 88 bits.
        [BINARY_VERIFIED TC03] ooc (AdvancedStashStackable=1) has quantity - proven by
        item alignment: only with 9-bit quantity does the next item (ka3) parse correctly.

        Rule: AdvancedStashStackable=1 in misc.txt -> item has 9-bit quantity field.
        """
        return code.lower() in self._quantity_codes


# Module-level singleton - loaded once, reused for all parses.
_ITEM_TYPE_DB = ItemTypeDatabase()


def get_item_type_db() -> ItemTypeDatabase:
    """Return the module-level item type database singleton."""
    return _ITEM_TYPE_DB


SCHEMA_VERSION_ITEM_TYPES: int = 1


def load_item_types(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`ItemTypeDatabase` via the Iron Rule.

    Reads all four source files (``armor.txt``, ``weapons.txt``,
    ``misc.txt``, ``itemtypes.txt``) through the shared
    :class:`CASCReader` - Reimagined mod install first, D2R Resurrected
    CASC fallback per file independently.  This is the
    MINIMUM game data needed for correct item parsing - without it
    every item reads as ``ItemCategory.UNKNOWN`` and the binary
    field layout cannot be determined.

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
            :class:`GamePaths` and memoises the result process-
            wide across loaders.
        cache_dir: Optional cache root override (tests route this
            into a ``tmp_path``).
    """

    def _build() -> None:

        armor_rows = read_game_data_rows("data:data/global/excel/armor.txt")
        weapon_rows = read_game_data_rows("data:data/global/excel/weapons.txt")
        misc_rows = read_game_data_rows("data:data/global/excel/misc.txt")
        itemtypes_rows = read_game_data_rows("data:data/global/excel/itemtypes.txt")

        if not (armor_rows or weapon_rows or misc_rows or itemtypes_rows):
            logger.error(
                "No game data found in mod or CASC - item type detection will "
                "fail; all items will be treated as UNKNOWN."
            )
            return

        get_item_type_db().load_from_rows(
            armor_rows,
            weapon_rows,
            misc_rows,
            itemtypes_rows,
            source="data:data/global/excel/*.txt (Iron Rule)",
        )

    cached_load(
        name="item_types",
        schema_version=SCHEMA_VERSION_ITEM_TYPES,
        singleton=get_item_type_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )
