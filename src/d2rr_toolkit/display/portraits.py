"""
src/d2rr_toolkit/display/portraits.py
=====================================
Resolve CASC asset paths for character and mercenary portraits.

The HD class and merc icons live at stable, well-known paths inside the
D2R CASC archive. This module is pure path arithmetic - it does not read
from CASC itself. Callers (e.g. the GUI sprite pipeline) feed the returned
paths into their CASC reader to fetch the actual sprite bytes.

Two resolvers:

* :func:`class_portrait_path` - the class icon used as the "profile
  picture" in the character panel. Keyed by the binary class ID stored
  in the D2S header (``character_class``).

* :func:`merc_portrait_path` - the hireling icon matching the merc's
  class. Keyed by the hireling class name from hireling.txt (resolved
  by :class:`d2rr_toolkit.game_data.hireling.HirelingDatabase`).

Both return a CASC path string (``"data:..."``) or ``None`` when no
portrait exists for the given input. All paths are ``.sprite`` assets
that the existing sprite pipeline can decode.

[SOURCE: Verified against D2R v105 CASC archive - 175804 paths total,
 8 class ``.frontend`` sprites and 4 merc icons present.]
"""

# Binary class ID -> CASC portrait path.
#
# The asset name follows Blizzard's convention "<classname>icon.sprite"
# under `data/hd/global/ui/hireables/`. Despite the folder name, these
# icons are used throughout the UI for class identification (main panel,
# party list, friend list, ...) - not only on the hireling selection
# screen. The lowend variant sits next to the full one and is omitted
# here because the GUI falls back to the full-res sprite automatically.
#
# Class ID order matches d2rr_toolkit.game_data.charstats.ClassDefinition
# (0=Amazon ... 7=Warlock, Reimagined-extended).
_CLASS_PORTRAITS: dict[int, str] = {
    0: "data:data/hd/global/ui/hireables/amazonicon.sprite",
    1: "data:data/hd/global/ui/hireables/sorceressicon.sprite",
    2: "data:data/hd/global/ui/hireables/necromancericon.sprite",
    3: "data:data/hd/global/ui/hireables/paladinicon.sprite",
    4: "data:data/hd/global/ui/hireables/barbarianicon.sprite",
    5: "data:data/hd/global/ui/hireables/druidicon.sprite",
    6: "data:data/hd/global/ui/hireables/assassinicon.sprite",
    7: "data:data/hd/global/ui/hireables/warlockicon.sprite",
}

# Hireling class name (from hireling.txt) -> CASC merc icon path.
#
# The 4 hireling families each have one distinct icon. Subtypes (fire /
# cold / holy / might / ...) and difficulties share the same icon - the
# engine simply tints them at runtime, which the GUI can replicate later
# via the existing invtransform pipeline if needed.
#
# Iron Wolves are spelled "Eastern Sorceror" in hireling.txt (Blizzard
# data typo preserved verbatim); Reimagined keeps the same spelling.
_MERC_PORTRAITS: dict[str, str] = {
    "Rogue Scout": "data:data/hd/global/ui/hireables/rogueicon.sprite",
    "Desert Mercenary": "data:data/hd/global/ui/hireables/desertmercenaryicon.sprite",
    "Eastern Sorceror": "data:data/hd/global/ui/hireables/act3hireableicon.sprite",
    "Iron Wolf": "data:data/hd/global/ui/hireables/act3hireableicon.sprite",
    "Barbarian": "data:data/hd/global/ui/hireables/barbhirable_icon.sprite",
}


def class_portrait_path(character_class_id: int) -> str | None:
    """Return the CASC path for the player-class portrait.

    Args:
        character_class_id: The binary class ID from the D2S header
            (``CharacterHeader.character_class``). 0-7 for D2R Reimagined.

    Returns:
        CASC path string, or ``None`` if the class ID is unknown.
    """
    return _CLASS_PORTRAITS.get(character_class_id)


def merc_portrait_path(hireling_class: str) -> str | None:
    """Return the CASC path for a mercenary portrait.

    Args:
        hireling_class: The ``Hireling`` column value from hireling.txt
            for the merc's type row (``MercenaryHeader.hireling_class``).

    Returns:
        CASC path string, or ``None`` if the class name is unknown.
        An empty string or unknown name returns ``None``.
    """
    if not hireling_class:
        return None
    return _MERC_PORTRAITS.get(hireling_class)
