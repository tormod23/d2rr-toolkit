"""D2S/D2I binary format constants.

Tags: [BV] = binary-verified, [SPEC_ONLY] = from spec, not yet verified.
"""


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
"""Bit 13: 'picked up since last save' transient flag. [BV] across reference
implementations as the IS_NEW marker.

The game sets this bit when an item enters the inventory and clears it on
the next save. It is observed set in d2s (character) saves but NEVER set in
d2i (shared stash) saves. The :func:`writers.item_utils.clear_d2s_only_flags`
helper strips this bit from every item written to a d2i to maintain that
invariant.

Secondary use: on simple (compact) items, the bit doubles as a 'this is a
gem-class item' discriminator under the v105 simple-item encoder. On
extended items it remains the transient pickup flag only.
"""

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

ITEM_BIT_FORMAT_SENTINEL: int = 23
"""Bit 23: always-1 format sentinel for v87+ items. [BV].

Set to 1 on every observed v87+ (LoD Expansion + D2R + v105 Reimagined) item.
Earlier item formats (v86 and below) wrote 0 here. Format-version sentinel,
not informational - the game uses it to detect the item-record schema.

Any encode path that synthesizes an item from scratch MUST hard-set this to
1. Round-trip parsers preserve the original value.
"""

# Backwards-compat alias - older code referenced this constant by its
# pre-decode name. New call sites should use ITEM_BIT_FORMAT_SENTINEL.
ITEM_BIT_UNKNOWN_23: int = ITEM_BIT_FORMAT_SENTINEL
"""Deprecated alias for :data:`ITEM_BIT_FORMAT_SENTINEL`."""

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
"""Online-server-data flag offset from ext_start. [BV].

This is a 1-bit ``has_online_payload`` flag (historically called
``timestamp_unknown_bit`` in the toolkit; the new name is more accurate per
external format documentation). When set, an additional payload follows:

  - Misc / gem / ring / amulet / charm / rune items: 128 bits of
    server-side metadata (96 bits in pre-D2R formats v87..v96).
  - All other item categories: 3 bits.

The payload encodes server-side state for online characters (UTC timestamp,
account / server-instance hash). For local single-player saves the flag is
observed 0 across every fixture in the test corpus, so the follow-on
payload is not currently parsed - we treat the bit as an unconditional
1-bit consume and assume the payload is absent.

Note: position shifts if has_gfx or has_class are set earlier in the header.
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
"""max_durability BASE field width on weapons. [BV TC09/TC33].

The 8-bit value is the BASE max_dur from items.txt, NOT the
effective max after ``+%Increased Maximum Durability`` affixes.
The game computes the effective max at display time as
``base_max * (1 + sum_of_max_dur_affixes)``.

Example (TC34 / Superior Club, ``+12% Increased Maximum
Durability``): file stores base_max = 250 (8-bit), in-game tooltip
shows "Durability: 280 of 280" because effective max = 250 * 1.12.
"""

WEAPON_WIDTH_CUR_DUR: int = 10
"""cur_durability field width on weapons. [BV TC34/Superior Club].

10-bit field, capable of representing values 0..1023. Stores the
EFFECTIVE current durability (post-affix), unlike ``max_dur`` which
stores the BASE pre-affix value. This split is what allows
``cur_dur`` to legitimately exceed the on-disk ``max_dur``: the
displayed max is ``base_max * (1 + max_dur_affix%)``, which can
push past 255 even when the base fits in 8 bits.

## Verification (TC34, README cross-checked)

  Item                       file_max  file_cur  README max/cur  Affix
  -------------------------  --------  --------  --------------  --------------
  Superior Club  (5,5)       250       280       280 / 280       +12% Max Dur
  Superior Leather Armor     24        26        26 / 26         +11% Max Dur
  Superior Boots             12        13        13 / 13         +14% Max Dur
  Superior Hand Axe (3,5)    250       217       250 / 217       (no Max Dur)
  Damaged Club               82        72        82 / 72         (no Max Dur)
  Viper Thirst (Rare)        250       250       250 / 250       (no Max Dur)

For every item with a ``+Max Dur`` affix the parser's ``cur_dur``
matches the README's effective cur. For items WITHOUT the affix
both ``max_dur`` and ``cur_dur`` match the README directly.

## Throwing weapons

Throwing weapons (Javelins, Throwing Knives, Glaive variants) carry
the same 10-bit ``cur_dur`` field on the wire, but the in-game
tooltip shows ``Quantity X / Y`` instead of a Durability line. The
``cur_dur`` field for throwing weapons therefore appears to violate
``cur <= max`` (e.g., TC34 / Javelin: file_cur = 693, file_max = 250)
but this is invisible to the player and irrelevant to game logic - the
durability field is simply not user-facing for that item class.

DO NOT try to "fix" the 10-bit interpretation back to 8+2 because of
throwing-weapon ``cur > max`` observations: the Superior Club case
above (in-game cur=280 in the tooltip, parser cur=280, parser max=250
from 8-bit base) proves the 10-bit reading is the right model. Any
"8-bit cur + 2-bit post" interpretation would give the Superior Club
``cur = 24`` and contradict the in-game tooltip.

When ``max_dur == 0`` (Phase Blade / ``7cr``), cur_dur is omitted
and the parser falls back to a 1-bit padding read - see the
weapon-path parse code for the ``max_dur > 0`` gating.
"""

# Back-compat alias - older code referenced WEAPON_WIDTH_POST_DUR as
# a separate 2-bit field. With the 10-bit cur_dur model that field
# no longer exists; the constant resolves to 0 so any leftover
# ``reader.read(WEAPON_WIDTH_POST_DUR)`` is a no-op rather than
# silently consuming bits.
WEAPON_WIDTH_POST_DUR: int = 0
"""Deprecated. Set to 0 (no separate field) under the 10-bit cur_dur
model. The bits formerly read here are now the high 2 bits of
``WEAPON_WIDTH_CUR_DUR`` and encode the high 2 bits of the EFFECTIVE
current durability for melee weapons with ``+Max Dur`` affixes."""


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
    # The Huffman alphabet covers exactly 36 glyphs: a-z (lowercase),
    # 0-9, and space. There is NO encoding for underscore "_" or any
    # uppercase / punctuation character. Item codes containing such
    # characters cannot be Huffman-encoded; the encoder asserts on
    # encounter to fail loud rather than emitting wrong bits.
}


# ============================================================
# D2I (SHARED STASH) FILE-FORMAT CONSTANTS
# ============================================================
#
# A .d2i file is a sequence of "pages" (called "tabs" or "sections" in
# this codebase). Each page is a self-contained block:
#
#   bytes 0x00..0x03   magic 0x55AA55AA  (same as .d2s)
#   bytes 0x04..0x07   header_format_flag  (u32 LE)
#   bytes 0x08..0x0B   version             (u32 LE = 105 for Reimagined)
#   bytes 0x0C..0x0F   gold                (u32 LE, capped per-page)
#   bytes 0x10..0x13   page_length         (u32 LE, full size of THIS page)
#   bytes 0x14..0x3F   padding (mostly zero)
#   bytes 0x40..0x41   "JM" marker (0x4A 0x4D)
#   bytes 0x42..0x43   item_count          (u16 LE)
#   bytes 0x44..0x44+N item blobs          (variable, bit-packed)
#
# After ``page_length`` bytes the next page starts (also at a 0x55AA55AA
# magic). The Reimagined SharedStash always ends with a 7th page whose
# +0x40 marker is ``0xC0EDEAC0`` instead of ``"JM"`` - this is a v105
# audit/log block that the game validates against the actual stash items
# on load. Removing items without updating the audit block causes the
# game to reject the file with "Failed to join Game".
# ============================================================

D2I_PAGE_HEADER_SIZE: int = 0x44
"""Size of the per-page header in bytes (64-byte fixed header + 4-byte
JM-marker-and-count). [BV] across all reference implementations - empty
pages have ``page_length == 68`` exactly."""

# ── Page-header field offsets ──

D2I_PAGE_OFFSET_MAGIC: int = 0x00
"""Magic 0x55AA55AA (4 bytes)."""

D2I_PAGE_OFFSET_HEADER_FLAG: int = 0x04
"""Reimagined-vs-vanilla discriminator (u32 LE)."""

D2I_PAGE_OFFSET_VERSION: int = 0x08
"""File-format version (u32 LE = 105 for Reimagined v105)."""

D2I_PAGE_OFFSET_GOLD: int = 0x0C
"""Per-page gold (u32 LE). Capped at ``D2I_TAB_GOLD_MAX`` for shared tabs.

Was historically misidentified in the toolkit as an "always-static
non-checksum field". The static-looking value 0x002625A0 = 2,500,000
that we observed in two unrelated fixtures was the per-tab gold cap
written by the game when a tab held the maximum amount."""

D2I_PAGE_OFFSET_PAGE_LENGTH: int = 0x10
"""Total page length in bytes (u32 LE) - the next page starts at
``page_offset + page_length``."""

D2I_PAGE_OFFSET_JM_MARKER: int = 0x40
"""Position of the ``JM`` marker (or the audit-block discriminator
``0xC0EDEAC0`` for the trailing v105 page)."""

# ── Reimagined header-flag values ──

D2I_HEADER_FLAG_VANILLA: int = 0x00
"""``header_format_flag`` value on vanilla D2R (pre-v105) shared stash
files. The C++ general-purpose D2 editor's reference fixtures all show
this value."""

D2I_HEADER_FLAG_REIMAGINED: int = 0x02
"""``header_format_flag`` value on Reimagined (v105) shared stash files.

Combined with ``version == 105`` this is the cleanest single-test
discriminator for "is this file a Reimagined SharedStash". Every
Reimagined .d2i in the test corpus carries this value at offset 0x04
of EVERY page header (not just the first)."""

# ── Gold caps (Reimagined v105) ──

D2I_TAB_GOLD_MAX: int = 2_500_000
"""Maximum gold the game allows in a single shared-stash tab. Encoded
in the per-page ``gold`` field at offset 0x0C of each page header.

Confirmed by reference editor source code that hard-clamps gold writes
to this value; we add a parser warning if a parsed value exceeds it.
"""

D2I_REIMAGINED_TAB_COUNT: int = 5
"""Number of regular (gold-bearing) shared-stash tabs in Reimagined v105.

Reimagined increased the count from 3 to 5 with Reign of the Warlock.
Earlier Reimagined versions had 3 tabs of 2.5M each (= 7.5M total);
v105 has 5 tabs of 2.5M each (= 12.5M total). The 6th regular tab
(index 5, "Gems / Materials / Runes") has no gold field, and the 7th
page is the audit-block (also no gold)."""

D2I_REIMAGINED_TOTAL_GOLD_MAX: int = D2I_TAB_GOLD_MAX * D2I_REIMAGINED_TAB_COUNT
"""Total gold that fits across all 5 shared tabs combined (12,500,000)."""

# ── Audit-block / trailing v105 page ──

D2I_AUDIT_BLOCK_MARKER: bytes = b"\xc0\xed\xea\xc0"
"""4-byte marker that appears at offset 0x40 of the trailing page,
where the ``JM`` marker would normally be. Identifies the page as the
v105 audit/log block (Reimagined-only, absent from vanilla D2R files)."""

D2I_AUDIT_RECORD_SIZE: int = 10
"""Size of a single record in the audit block.

Empirically derived layout:
  bytes 0..3  field_a   (u32 LE; appears to be a 32-bit hash/ID)
  bytes 4..5  marker    (u16 LE = 0x01C3 - constant per-record discriminator)
  bytes 6..9  field_b   (u32 LE; small integers, mutmasslich counters)

Records sit after a 20-byte sub-header that follows the 4-byte marker.
"""

D2I_AUDIT_RECORD_MARKER: int = 0x01C3
"""Constant u16 LE value found at bytes 4..5 of every audit-block record.
Used as a stride-validation marker when scanning the audit block."""


# ============================================================
# D2S (CHARACTER) GOLD CAPS
# ============================================================

D2S_PERSONAL_STASH_GOLD_MAX: int = 2_500_000
"""Maximum gold storable in the character's personal stash. [BV] from
the Reimagined gameplay rules - same cap as a single shared-stash tab.
"""

D2S_CHARACTER_GOLD_PER_LEVEL: int = 10_000
"""Gold a character can carry equals ``character_level * 10_000``.

The cap scales linearly with character level: a level-1 char carries
10k, a level-99 char carries 990k. This is a soft display cap; the
field width itself supports much larger values, but the game refuses
to deposit gold above ``level * 10_000`` from drops or trades."""
