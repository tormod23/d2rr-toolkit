"""D2S/D2I binary format constants.

Tags: [BV] = binary-verified, [SPEC_ONLY] = from spec, not yet verified.
"""

from __future__ import annotations


# ============================================================
# FILE SIGNATURE & VERSION
# ============================================================

D2S_SIGNATURE: int = 0xAA55AA55
"""Magic bytes at offset 0x00. [BV]-TC10."""

D2S_VERSION_REIMAGINED: int = 105
"""D2S version for D2R Reimagined mod. [BV]-TC10.
Spec originally assumed 98 - actual binary shows 105 (0x69).
"""

SUPPORTED_VERSIONS: tuple[int, ...] = (105,)
"""Versions this parser fully supports. [BV]."""


# ============================================================
# HEADER FIELD OFFSETS
# These are BYTE offsets from the start of the file.
# [BV]
# ============================================================

OFFSET_SIGNATURE: int = 0x0000
"""Signature field offset. [BV]."""

OFFSET_VERSION: int = 0x0004
"""Version field offset. [BV]."""

OFFSET_FILE_SIZE: int = 0x0008
"""File size field offset. [BV]."""

OFFSET_CHECKSUM: int = 0x000C
"""Checksum field offset. [BV]."""

OFFSET_STATUS: int = 0x0014
"""Character status byte offset. [BINARY_VERIFIED TC01-TC10, 7 chars].
D2R v105 shifted -16 from classic D2 (0x24).

Status byte bit layout in D2R v105 [BINARY_VERIFIED HCLives/HCDied/5 SC chars]:
  bit 2 (0x04): Hardcore -- 1 if HC, 0 if SC
  bit 3 (0x08): Died flag -- 1 if character has died (HC: permanently dead;
                              SC: historical flag, char has died at some point)
  Expansion is IMPLICIT in D2R v105 (all D2R characters are Expansion;
  there is no dedicated Expansion bit as in classic D2's bit 5).

Verification matrix:
  HCLives    (HC, alive) = 0x04 (bit 2 only)          -> HC, not died
  HCDied     (HC, dead)  = 0x0C (bit 2 + bit 3)        -> HC, died (permadead)
  MrLockhart (SC)        = 0x08 (bit 3 only)           -> SC, died-flag set
  StraFoHdin (SC)        = 0x08 (bit 3 only)           -> SC, died-flag set
"""

OFFSET_PROGRESSION: int = 0x0015
"""Character progression byte offset. [BINARY_VERIFIED TC01-TC10, 5 chars].
D2R v105 shifted -16 from classic D2 (0x25).

Values (expansion characters):
  0      = no title
  5      = Normal completed (Slayer / Destroyer HC)
  10     = Nightmare completed (Champion / Conqueror HC)
  15     = Hell completed (Patriarch-Matriarch / Guardian HC)

All 5 test chars (MrLockhart, FrozenOrbHydra, VikingBarbie, StraFoHdin, AAAAA)
show 0x0F = 15 which matches their in-game Patriarch/Matriarch titles.
"""

OFFSET_CLASS: int = 0x0018
"""Character class byte offset. [BV]-TC10.
Spec said 0x28 - actual binary shows 0x18.
"""

OFFSET_LEVEL: int = 0x001B
"""Character level byte offset. [BV]-TC10.
Spec said 0x2B - actual binary shows 0x1B.
"""

OFFSET_NAME: int = 0x012B
"""Character name start offset (null-terminated ASCII). [BV]-TC10.
Spec said 0x14 - actual binary shows 0x12B.
"""

OFFSET_TIMESTAMP_LAST_SAVED: int = 0x0020
"""'Last saved' UNIX timestamp (uint32 LE). Updated by the game engine on
every save. The D2S writer MUST update this to ``int(time.time())`` before
computing the checksum - the game rejects files with a stale timestamp as
corrupt ('Failed to join Game').
[BINARY_VERIFIED TC62-TC66, 7 saves spanning 2026-04-11..2026-04-12]
"""

# ── Mercenary header (14 bytes starting at 0xA1) [BV] ──
# Layout (all little-endian):
#   0xA1 u16 : merc_dead        0=alive, 1=dead (HC permadeath)
#   0xA3 u32 : merc_control     random control seed
#   0xA7 u16 : merc_name_id     index into localized merc name list
#   0xA9 u16 : merc_type        row index into hireling.txt
#   0xAB u32 : merc_experience  total merc exp
# The 14-byte block is all-zero when the character never hired a merc.
# Verified on 5 v105 Reimagined saves.
OFFSET_MERC_DEAD: int = 0x00A1
OFFSET_MERC_CONTROL: int = 0x00A3
OFFSET_MERC_NAME_ID: int = 0x00A7
OFFSET_MERC_TYPE: int = 0x00A9
OFFSET_MERC_EXP: int = 0x00AB
MERC_HEADER_SIZE: int = 14

HEADER_SIZE_V105: int = 833
"""Total header size in bytes for v105. [BV]-TC10.
Spec said 765 - actual binary shows 833 (+68 bytes).
'gf' stats marker found consistently at byte 833.
"""


# ============================================================
# SECTION MARKER OFFSETS (all +68 vs v97 spec) [BV]
# ============================================================

OFFSET_QUEST_SECTION: int = 403
"""'Woo!' quest header offset. [BV]02/03. Spec: 335."""

OFFSET_WAYPOINT_SECTION: int = 701
"""'WS' waypoint header offset. [BV]02/03. Spec: 633."""

OFFSET_NPC_SECTION: int = 782
"""'w4' NPC header offset. [BV]02/03. Spec: 714."""

OFFSET_STATS_SECTION: int = 833
"""'gf' stats header offset. [BV]02/03. Spec: 765."""

SECTION_MARKER_QUEST: bytes = b"Woo!"
"""Quest section magic bytes. [BV]."""

SECTION_MARKER_WAYPOINT: bytes = b"WS"
"""Waypoint section magic bytes. [BV]."""

SECTION_MARKER_NPC: bytes = b"w4"
"""NPC section magic bytes. [BV]."""

SECTION_MARKER_STATS: bytes = b"gf"
"""Stats section magic bytes. [BV]."""

SECTION_MARKER_SKILLS: bytes = b"if"
"""Skills section magic bytes. [BV]."""

SECTION_MARKER_ITEMS: bytes = b"JM"
"""Item list header magic bytes. [BV]. Only on list, never per-item."""

SECTION_MARKER_MERC_START: bytes = b"jf"
"""Mercenary section start marker. [BV]."""

SECTION_MARKER_MERC_END: bytes = b"kf"
"""Mercenary section end marker. [BV]."""


# ============================================================
# CHARACTER CLASSES [BINARY_VERIFIED where noted]
# ============================================================

CLASS_AMAZON: int = 0
"""Amazon class ID. [BV]."""

CLASS_SORCERESS: int = 1
"""Sorceress class ID. [SPEC_ONLY]."""

CLASS_NECROMANCER: int = 2
"""Necromancer class ID. [SPEC_ONLY]."""

CLASS_PALADIN: int = 3
"""Paladin class ID. [BV]09/10."""

CLASS_BARBARIAN: int = 4
"""Barbarian class ID. [BV]02."""

CLASS_DRUID: int = 5
"""Druid class ID. [SPEC_ONLY]."""

CLASS_ASSASSIN: int = 6
"""Assassin class ID. [SPEC_ONLY]."""

CLASS_WARLOCK: int = 7
"""Warlock class ID (new class in Reign of the Warlock). [BV]."""

# NOTE: a hardcoded CLASS_NAMES dict previously lived here. It was
# deprecated in favour of ``charstats.get_class_name(id)`` (which reads
# charstats.txt at runtime) on 2026-03-30 and carried no callers in
# src/ or tests/.  If you need a runtime class-name lookup, use:
#
#     from d2rr_toolkit.game_data.charstats import get_charstats_db
#     name = get_charstats_db().get_class_name(class_id)


# ============================================================
# SKILLS SECTION
# ============================================================

SKILLS_SECTION_SIZE: int = 32
"""Total skills section size in bytes (2 header + 30 skill bytes).
[BV]02/03: JM_offset - if_offset = 32 in all files.
"""

SKILLS_DATA_SIZE: int = 30
"""Number of skill bytes (one byte per skill slot). [BV]."""


# ============================================================
# ITEM LIST
# ============================================================

ITEM_LIST_HEADER_SIZE: int = 4
"""'JM' (2 bytes) + uint16 item count (2 bytes). [BV]."""

STATS_TERMINATOR: int = 0x1FF
"""9-bit all-ones value that terminates the stats section. [SPEC_ONLY]."""

ITEM_STATS_TERMINATOR: int = 0x1FF
"""9-bit all-ones value that terminates an item's magical property list.
[BV]09/10.
"""


# ============================================================
# ITEM FLAG BIT POSITIONS (item-relative, from bit 0 of each item)
# All [BV] unless noted. Source: TC01-TC10.
# ============================================================

ITEM_BIT_IDENTIFIED: int = 4
"""Bit 4: Item has been identified. [BV]."""

ITEM_BIT_SOCKETED: int = 11
"""Bit 11: Item has sockets. [BV]."""

ITEM_BIT_PICKED_UP: int = 13
"""Bit 13: Picked up since last save. [UNKNOWN]."""

ITEM_BIT_IS_EAR: int = 16
"""Bit 16: Item is a player ear (PvP trophy). [BV]."""

ITEM_BIT_STARTER_ITEM: int = 17
"""Bit 17: Default starter item (given at character creation).
[BV](value=1), TC07 (value=0, bought item).
"""

ITEM_BIT_SIMPLE: int = 21
"""Bit 21: Simple/compact item (no extended data). [BV].
Potions, gold, and some misc items are simple.
"""

ITEM_BIT_ETHEREAL: int = 22
"""Bit 22: Item is ethereal. [BV] (all tested = 0, flag confirmed)."""

ITEM_BIT_UNKNOWN_23: int = 23
"""Bit 23: Unknown, always 1 in all tested items. [UNKNOWN]."""

ITEM_BIT_PERSONALIZED: int = 24
"""Bit 24: Item is personalized (has player name). [BV]."""

ITEM_BIT_RUNEWORD: int = 26
"""Bit 26: Item is a runeword. [BV] (all tested = 0, flag confirmed)."""

# Location / position fields
ITEM_BIT_LOCATION_ID: int = 35
"""Bits 35-37: Item location (3 bits). [BV].
Spec said 34-36 - actual is 35-37 (+1 shift).
"""

ITEM_BIT_EQUIPPED_SLOT: int = 38
"""Bits 38-41: Equipped slot ID (4 bits). [BV].
Spec said 37-40 - actual is 38-41 (+1 shift).
"""

ITEM_BIT_POSITION_X: int = 42
"""Bits 42-45: X position in inventory/stash grid (4 bits). [BV]."""

ITEM_BIT_POSITION_Y: int = 46
"""Bits 46-49: Y position in inventory/stash grid (4 bits). [BV]."""

ITEM_BIT_PANEL_ID: int = 50
"""Bits 50-52: Panel/storage area ID (3 bits). [BV]."""

ITEM_BIT_HUFFMAN_START: int = 53
"""Bit 53: Start of Huffman-encoded item code. [BV]-TC10.
Spec said 60 - actual binary shows 53 (-7 bits).
"""


# ============================================================
# LOCATION & PANEL IDs [BINARY_VERIFIED where noted]
# ============================================================

LOCATION_STORED: int = 0
"""Item is stored (check panel_id for where). [BV]08/09/10."""

LOCATION_EQUIPPED: int = 1
"""Item is equipped on character. [BV]."""

LOCATION_BELT: int = 2
"""Item is in the belt. [BV]07."""

LOCATION_CURSOR: int = 4
"""Item is on the cursor (being moved). [SPEC_ONLY]."""

LOCATION_SOCKETED: int = 6
"""Item is socketed in another item. [SPEC_ONLY]."""

LOCATION_NAMES: dict[int, str] = {
    0: "Stored",
    1: "Equipped",
    2: "Belt",
    4: "Cursor",
    6: "Socketed",
}

PANEL_NONE: int = 0
"""No panel (equipped or belt items). [BV]."""

PANEL_INVENTORY: int = 1
"""Personal inventory. [BV]08/09/10."""

PANEL_CUBE: int = 4
"""Horadric Cube. [SPEC_ONLY]."""

PANEL_STASH: int = 5
"""Personal stash. [SPEC_ONLY]."""

PANEL_NAMES: dict[int, str] = {
    0: "None",
    1: "Inventory",
    4: "Cube",
    5: "Stash",
}

SLOT_NAMES: dict[int, str] = {
    0: "Not equipped",
    1: "Head",
    2: "Neck / Amulet",
    3: "Torso",  # [BV]
    4: "Right Hand",
    5: "Left Hand",
    6: "Right Ring",
    7: "Left Ring",
    8: "Waist / Belt",
    9: "Feet / Boots",
    10: "Hands / Gloves",
    11: "Alt Right Hand",
    12: "Alt Left Hand",
}


# ============================================================
# ITEM QUALITY IDs [SPEC_ONLY unless noted]
# ============================================================

QUALITY_LOW: int = 1
QUALITY_NORMAL: int = 2  # [BV]09/10
QUALITY_SUPERIOR: int = 3
QUALITY_MAGIC: int = 4
QUALITY_SET: int = 5
QUALITY_RARE: int = 6
QUALITY_UNIQUE: int = 7
QUALITY_CRAFTED: int = 8

QUALITY_NAMES: dict[int, str] = {
    1: "Low Quality",
    2: "Normal",
    3: "Superior",
    4: "Magic",
    5: "Set",
    6: "Rare",
    7: "Unique",
    8: "Crafted",
}


# ============================================================
# EXTENDED ITEM FIELD OFFSETS (relative to ext_start)
# ext_start = ITEM_BIT_HUFFMAN_START + huffman_bits_consumed
# ============================================================

EXT_OFFSET_UNIQUE_ID: int = 0
"""unique_item_id field offset from ext_start. Width = 35 bits.
[BV]09/10. Spec said 32 bits - actual is 35.
"""

EXT_WIDTH_UNIQUE_ID: int = 35
"""unique_item_id field width in bits. [BV]. NOT 32."""

EXT_OFFSET_ILVL: int = 35
"""item_level (iLVL) field offset from ext_start. [BV]09/10."""

EXT_WIDTH_ILVL: int = 7
"""item_level field width in bits. [BV]."""

EXT_OFFSET_QUALITY: int = 42
"""Quality field offset from ext_start. [BV]09/10."""

EXT_WIDTH_QUALITY: int = 4
"""Quality field width in bits. [BV]."""

EXT_OFFSET_HAS_GFX: int = 46
"""has_custom_graphics flag offset from ext_start. [BV]."""

EXT_OFFSET_HAS_CLASS: int = 47
"""has_class_specific_data flag offset from ext_start. [BV].
Note: if has_custom_graphics=1, this shifts by 3 bits.
"""

EXT_OFFSET_TIMESTAMP: int = 48
"""timestamp_unknown_bit offset from ext_start. [BV].
Note: shifts if has_gfx or has_class are set.
Purpose of this bit is [UNKNOWN].
"""

EXT_OFFSET_TYPE_SPECIFIC: int = 49
"""Start of item-type-specific data, relative to ext_start. [BV].
Note: shifts if has_gfx or has_class are set, or if quality-specific data exists.
Actual offset must be computed dynamically - this constant assumes no optional fields.
"""


# ============================================================
# ARMOR-TYPE ITEM FIELDS (from type_start)
# type_start = ext_start + EXT_OFFSET_TYPE_SPECIFIC (adjusted for optional fields)
# ============================================================

ARMOR_OFFSET_DEFENSE: int = 0
"""armor_defense field offset from type_start. [BV]."""

ARMOR_WIDTH_DEFENSE: int = 11
"""armor_defense field width in bits. [BV]."""

ARMOR_SAVE_ADD_DEFENSE: int = 10
"""Save Add for armor defense: displayed_value = raw - 10. [BV]."""

ARMOR_OFFSET_MAX_DUR: int = 11
"""max_durability field offset from type_start. [BV]."""

ARMOR_OFFSET_CUR_DUR: int = 19
"""cur_durability field offset from type_start. [BV]."""

ARMOR_WIDTH_MAX_DUR: int = 8
"""max_durability field width in bits. [BV].

Evidence: TC08 (max=12), TC09 (max=250), TC10 (max=12) all decode with
8 bits. The Reimagined armor.txt caps base durability at 250 by design
(verified across 523 armor+weapon rows), so the field never saturates
the 8-bit space - 250 sits at 98% of the 0..255 range.
"""

ARMOR_WIDTH_CUR_DUR: int = 10
"""cur_durability field width in bits. [BV].

Evidence: across 612 armor items parsed from every TC fixture, the
upper 2 bits of this field are ALWAYS zero - consistent with the
underlying value fitting in 8 bits because ``cur_dur <= max_dur <= 250``
for all fixture data. The 10-bit layout is adopted as the format spec
because it is observationally equivalent to ``8 + 2 (padding)`` for
every item we have seen, and a 10-bit single-field encoding requires
no appeal to "unknown" / "reserved" bits in an otherwise densely-
packed binary.

The weapon branch uses a DIFFERENT layout - ``8 + 8 + 2`` where the
trailing 2 bits CAN be non-zero (observed 0b01 and 0b10 in 38 / 429
weapon items across the fixtures) and therefore cannot be absorbed
into a 10-bit cur_dur without producing impossible cur > max values.
See ``parsers/d2s_parser_items.py`` weapon-path comments.
"""

# Total width of the cur_dur read (armor-only).
ARMOR_WIDTH_DURABILITY: int = ARMOR_WIDTH_MAX_DUR
"""Back-compat alias. Prefer ``ARMOR_WIDTH_MAX_DUR`` at new call sites.

The old name bundled "both max and cur are 8 bits" into a single
constant. That was correct observationally but implied a symmetry
that doesn't hold once cur_dur is read as a 10-bit field. New code
should name the field it reads explicitly.
"""


# ============================================================
# WEAPON-TYPE ITEM FIELDS
# ============================================================

WEAPON_WIDTH_MAX_DUR: int = 8
"""max_durability field width on weapons. [BV TC09/TC33]."""

WEAPON_WIDTH_CUR_DUR: int = 8
"""cur_durability field width on weapons. [BV TC09/TC33].

Weapons use 8 bits for cur_dur - NOT 10 like armor does. The weapon
branch has 2 trailing bits after cur_dur (``WEAPON_WIDTH_POST_DUR``)
that can be non-zero, so they cannot be absorbed into a 10-bit
cur_dur without producing impossible cur > max values. 38 of 429
weapon items across the fixtures show non-zero trailing bits.
"""

WEAPON_WIDTH_POST_DUR: int = 2
"""2 bits immediately after weapon cur_dur. [BV TC33] width.

[PARTIAL] Semantic meaning not fully established: observed values
are 0b00 (91.1%), 0b01 (2.3%), and 0b10 (6.5%) across 429 weapon
items, with 0b11 never observed. The distribution is correlated
with throwing vs melee status in ways the current analysis has not
fully decoded. Writers preserve these bits verbatim.

When ``max_dur == 0`` (Phase Blade / ``7cr``), cur_dur is omitted
and this field SHRINKS to 1 bit. See the weapon-path parse code
for the ``max_dur > 0`` gating.
"""


# ============================================================
# SIMPLE ITEM
# ============================================================

SIMPLE_ITEM_SOCKET_BIT_OFFSET: int = 0
"""Socket count bit offset after the Huffman code (relative to end of Huffman code).
[BV]: socket bit = 0 (no sockets) at expected position.
"""

SIMPLE_ITEM_SOCKET_BIT_WIDTH: int = 1
"""Simple item: 1 unknown bit after Huffman code, before GUID/quantity.
[BINARY_VERIFIED] TC07."""


# ============================================================
# STATS SECTION [BV]
# ============================================================

STATS_ID_WIDTH: int = 9
"""Stat ID field width in bits. [SPEC_ONLY] - terminator value 0x1FF confirmed."""

STATS_TERMINATOR_VALUE: int = 0x1FF
"""Value of the 9-bit stats terminator. [BV]."""


# ============================================================
# HUFFMAN TABLE [BV]
# Source: d07riv Phrozen Keep post. Confirmed by TC01-TC10.
# ============================================================

HUFFMAN_TABLE: dict[str, str] = {
    " ": "10",  # space = terminator [BV]
    "0": "11111011",
    "1": "1111100",
    "2": "001100",
    "3": "1101101",
    "4": "11111010",
    "5": "00010110",
    "6": "1101111",
    "7": "01111",
    "8": "000100",
    "9": "01110",
    "a": "11110",
    "b": "0101",
    "c": "01000",
    "d": "110001",
    "e": "110000",
    "f": "010011",
    "g": "11010",
    "h": "00011",
    "i": "1111110",
    "j": "000101110",
    "k": "010010",
    "l": "11101",
    "m": "01101",
    "n": "001101",
    "o": "1111111",
    "p": "11001",
    "q": "11011001",
    "r": "11100",
    "s": "0010",
    "t": "01100",
    "u": "00001",
    "v": "1101110",
    "w": "00000",
    "x": "00111",
    "y": "0001010",
    "z": "11011000",
    # "_": [UNKNOWN] - underscore mapping not documented in d07riv table
}

