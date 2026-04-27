"""Inventory transform (color tinting) resolution for D2R Reimagined items.

Determines the invtransform color code for an item based on its quality,
type, and socketed gems. Returns the D2R color code string (e.g. "cred",
"lgld", "dpur") or None if no tinting applies.

The CSS/visual implementation of these color codes is NOT part of this
module -- that responsibility belongs to the GUI layer.

Tinting rules (D2R in-game behavior):
  - ARMOR + WEAPON: always tintable (Unique/Set/Magic prefix/suffix/Gem)
  - MISC Charms (cm1/cm2/cm3/cs1/cs2): only Unique invtransform
  - Other MISC (rings, amulets, jewels): never tinted

Priority: Unique > Set > Magic prefix > Magic suffix > First socketed gem

Usage::

    from d2rr_toolkit.display.invtransform import get_invtransform

    color_code = get_invtransform(item)
    # Returns e.g. "cred", "lgld", "dpur", or None
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedItem

logger = logging.getLogger(__name__)

# Gem item code -> invtransform color code.
# First socketed gem determines the item's sprite tint.
# Includes both vanilla quality tiers (chipped->perfect) and Reimagined
# single-tier gems (gm* codes, treated as perfect = full intensity).
GEM_COLOR_MAP: dict[str, str] = {
    # Vanilla Amethyst (chipped->flawless = light, perfect = dark)
    "gcv": "lpur",
    "gfv": "lpur",
    "gsv": "lpur",
    "gzv": "lpur",
    "gpv": "dpur",
    # Vanilla Sapphire
    "gcb": "cblu",
    "gfb": "cblu",
    "gsb": "cblu",
    "glb": "cblu",
    "gpb": "dblu",
    # Vanilla Emerald
    "gcg": "cgrn",
    "gfg": "cgrn",
    "gsg": "cgrn",
    "glg": "cgrn",
    "gpg": "dgrn",
    # Vanilla Ruby
    "gcr": "cred",
    "gfr": "cred",
    "gsr": "cred",
    "glr": "cred",
    "gpr": "dred",
    # Vanilla Topaz
    "gcy": "dyel",
    "gfy": "dyel",
    "gsy": "dyel",
    "gly": "dyel",
    "gpy": "dgld",
    # Vanilla Diamond
    "gcw": "whit",
    "gfw": "whit",
    "gsw": "whit",
    "glw": "whit",
    "gpw": "bwht",
    # Vanilla Skull
    "skc": "dgry",
    "skf": "dgry",
    "sku": "dgry",
    "skl": "dgry",
    "skz": "blac",
    # Reimagined single-tier gems (full intensity = same as perfect)
    "gmm": "dpur",  # Amethyst
    "gms": "dblu",  # Sapphire
    "gme": "dgrn",  # Emerald
    "gmr": "dred",  # Ruby
    "gmt": "dgld",  # Topaz
    "gmd": "bwht",  # Diamond
    "gmk": "blac",  # Skull
    "gmo": "dpur",  # Chaos Onyx
}

# Charm item codes that support Unique invtransform
_CHARM_CODES = frozenset({"cm1", "cm2", "cm3", "cs1", "cs2"})


def gem_to_invtransform(item_code: str) -> str | None:
    """Return the invtransform color for a gem/skull item code, or None.

    Covers all vanilla quality tiers (chipped->perfect) and Reimagined
    single-tier gems (gm* codes). Runes and jewels return None.
    """
    return GEM_COLOR_MAP.get(item_code.lower().strip())


def get_invtransform(item: "ParsedItem") -> str | None:
    """Resolve the invtransform color code for an item.

    Determines which color tint should be applied to the item's sprite
    in the inventory, following the D2R in-game priority rules.

    Socket children are read directly from ``item.socket_children`` -
    the legacy ``all_items`` / ``item_index`` parameters that used to
    locate them by walking the flat parser list have been removed.

    Args:
        item: The item to resolve tinting for.

    Returns:
        Color code string (e.g. "cred", "lgld", "dpur") or None if no
        tinting applies.
    """
    from d2rr_toolkit.game_data.item_types import ItemCategory, get_item_type_db
    from d2rr_toolkit.game_data.item_names import get_item_names_db

    type_db = get_item_type_db()
    names_db = get_item_names_db()

    quality_id = item.extended.quality if item.extended else 2
    item_category = type_db.classify(item.item_code)
    can_tint = item_category in (ItemCategory.ARMOR, ItemCategory.WEAPON)
    is_charm = item.item_code in _CHARM_CODES

    invtransform: str | None = None

    # 1. Unique invtransform: ARMOR + WEAPON + Charms
    if quality_id == 7 and item.unique_type_id is not None and names_db.is_loaded():
        if can_tint or is_charm:
            invtransform = names_db.get_unique_invtransform(item.unique_type_id)

    if can_tint and invtransform is None:
        # 2. Set invtransform
        if quality_id == 5 and item.set_item_id is not None:
            from d2rr_toolkit.game_data.sets import get_sets_db

            sets_db = get_sets_db()
            if sets_db.is_loaded():
                set_item_def = sets_db.get_set_item(item.set_item_id)
                if set_item_def and set_item_def.invtransform:
                    invtransform = set_item_def.invtransform

        # 3. Magic prefix/suffix transformcolor
        elif quality_id == 4 and names_db.is_loaded():
            if item.prefix_id is not None:
                invtransform = names_db.get_prefix_transformcolor(item.prefix_id)
            if invtransform is None and item.suffix_id is not None:
                invtransform = names_db.get_suffix_transformcolor(item.suffix_id)

        # 4. Gem socket color: first socketed gem determines color
        if invtransform is None and item.flags.socketed:
            from d2rr_toolkit.display.item_display import get_socket_child_codes

            child_codes = get_socket_child_codes(item, item.total_nr_of_sockets)
            if child_codes:
                invtransform = gem_to_invtransform(child_codes[0])

    return invtransform
