"""
Authoritative item display color logic.

Consolidates the "item code -> display color" mapping that was previously
duplicated across cli.py and gui/server.py into a single module.
"""

# ── D2R in-game colour codes (exact hex values) ────────────────────────────────
COLOR_MAGIC = "#4169E1"  # Royal Blue  - Magic items
COLOR_SET = "#00FF00"  # Lime Green  - Set items + item-specific set bonuses
COLOR_RARE = "#FFFF00"  # Yellow      - Rare items
COLOR_UNIQUE = "#BDB76B"  # Dark Khaki  - Unique items + set-wide bonuses
COLOR_CRAFTED = "#FFA500"  # Orange      - Crafted items
COLOR_GEM = "#89c9ff"  # Gem Cyan    - Reimagined gems
COLOR_REJUV = "#b300ff"  # Rejuv Purple - Rejuvenation potions
COLOR_ENCHANT = "#b300ff"  # Enchantment Purple - "Enchantments: x / n" label
COLOR_CORRUPT = "#ff5555"  # Corrupted Red - Worldstone shards, obsolete gems
COLOR_GRAB = "#ff87ff"  # Ethereal Pink - Grabber tools (pliers, Chaos Onyx)

# ── Quality -> colour mapping ───────────────────────────────────────────────────
# Used by both CLI (Rich markup) and GUI (HTML/CSS hex strings).
# Values are hex strings so they work in both contexts.
#
# This is the "quality indicator" color - i.e. the colour used for the
# item's SUBTYPE line ("Grand Charm") where the tier is announced. For
# most qualities the name line uses the same colour, but Crafted is
# special: the in-game tooltip renders the NAME line in Magic-blue
# (because a crafted item's name is a prefix-suffix pair just like a
# magic item) while the subtype line gets the distinct Crafted-orange.
# Consumers should call :func:`get_title_color` / :func:`get_subtype_color`
# instead of indexing this dict directly so the crafted special-case
# stays in one place.
QUALITY_COLORS: dict[int, str] = {
    1: "#808080",  # Low Quality (grey)
    2: "#FFFFFF",  # Normal (white)
    3: "#FFFFFF",  # Superior (bright white)
    4: COLOR_MAGIC,  # Magic
    5: COLOR_SET,  # Set
    6: COLOR_RARE,  # Rare
    7: COLOR_UNIQUE,  # Unique
    8: COLOR_CRAFTED,  # Crafted
}


def get_title_color(quality_id: int) -> str:
    """Return the colour for the item's **name** line (the title).

    Crafted items (quality 8) display their title in Magic-blue in the
    in-game tooltip - the affix-pair naming pattern they share with
    magic items outweighs the "crafted" distinction at the name level.
    The orange Crafted marker lives on the subtype line only (see
    :func:`get_subtype_color`). Every other quality uses its own
    tier colour for both lines.
    [BV FrozenOrbHydra "Ghoul Eye" charm, 2026-04-14]
    """
    if quality_id == 8:
        return COLOR_MAGIC
    return QUALITY_COLORS.get(quality_id, "#FFFFFF")


def get_subtype_color(quality_id: int) -> str:
    """Return the colour for the item's **subtype** line.

    The subtype line appears below the title and names the base item
    category (e.g. "Grand Charm", "Superior Crystal Sword"). In-game
    the subtype is coloured by the quality tier for every non-trivial
    quality (Magic/Set/Rare/Unique/Crafted). Low/Normal/Superior items
    do not repeat their name on a subtype line, so this helper is
    called only for qualities 4-8.
    """
    return QUALITY_COLORS.get(quality_id, "#FFFFFF")


# ── Lookup tables ───────────────────────────────────────────────────────────────
# Classic/Obsolete gem prefixes (ROTW vanilla, replaced by Reimagined gems)
OBSOLETE_GEM_PREFIXES = ("gc", "gf", "gs", "gl", "gz", "gp", "sk")
# Unique-colored material items
_UNIQUE_MATERIAL_CODES = {"mpa", "blc", "dia"}


def get_item_display_color(item_code: str, item_type: str, quality_id: int = 2) -> str:
    """Return the hex color string for an item based on its code, type, and quality.

    For "simple" / material-type items the colour is determined by item code and
    type (gems, runes, orbs, etc.).  For everything else the quality tier drives
    the colour.

    Parameters
    ----------
    item_code : str
        The 3-4 character item code (e.g. ``"r01"``, ``"rvl"``).
    item_type : str
        The item type string from ItemTypes (e.g. ``"gem0"``, ``"rune"``).
    quality_id : int, optional
        Quality tier (1-8).  Only used when no material-type override applies.
    """
    code = item_code.lower()

    # Gems
    if item_type.startswith("gem") or code == "1gc":
        if any(code.startswith(p) for p in OBSOLETE_GEM_PREFIXES):
            return COLOR_CORRUPT  # Obsolete classic gems
        return COLOR_GEM  # Reimagined gems, Gem Cluster

    # Orbs and Orb Stacks
    if code.startswith("oo") or code.startswith("ka") or item_type == "orbx":
        return COLOR_CRAFTED

    # Tools (pliers)
    if item_type == "grab":
        return COLOR_GRAB

    # Runes
    if item_type in ("rune", "runx"):
        return COLOR_CRAFTED

    # Worldstone Shards
    if code.startswith("xa"):
        return COLOR_CORRUPT

    # Rejuv Potions
    if code in ("rvs", "rvl"):
        return COLOR_REJUV

    # Keys, Quest Statues (ua1-ua5, NOT uap/uar which are armor)
    if code.startswith("pk") or (code.startswith("ua") and len(code) == 3 and code[2].isdigit()):
        return COLOR_CRAFTED

    # Token of Absolution, XP Potion
    if code in ("toa", "xpp"):
        return COLOR_CRAFTED

    # Horadric Cube + Gem Bag
    if code == "box":
        return COLOR_UNIQUE
    if code == "bag":
        return COLOR_CRAFTED

    # Uber essences
    if code in _UNIQUE_MATERIAL_CODES:
        return COLOR_UNIQUE

    # Fall back to quality-based color
    return QUALITY_COLORS.get(quality_id, "#FFFFFF")
