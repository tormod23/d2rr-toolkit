# Diablo II: Resurrected -- Save File Format Specification

> **Target Version:** D2R v105 "Reign of the Warlock" with D2R Reimagined mod
> **Purpose:** Binary format reference for `.d2s` (character) and `.d2i` (shared stash) files

---

## Table of Contents

1. [Version History and Save File Versions](#1-version-history-and-save-file-versions)
2. [General Binary Conventions](#2-general-binary-conventions)
3. [D2S File Format -- Character Save](#3-d2s-file-format----character-save)
   - [3.1 Header (833 bytes)](#31-header-833-bytes)
   - [3.2 Quest Data](#32-quest-data)
   - [3.3 Waypoint Data](#33-waypoint-data)
   - [3.4 NPC Data](#34-npc-data)
   - [3.5 Character Attributes / Stats](#35-character-attributes--stats)
   - [3.6 Skills](#36-skills)
   - [3.7 Item Lists](#37-item-lists)
   - [3.8 Corpse Data](#38-corpse-data)
   - [3.9 Mercenary Item Section (jf, Expansion)](#39-mercenary-item-section-jf-expansion)
   - [3.10 Iron Golem (Necromancer, Expansion)](#310-iron-golem-necromancer-expansion)
4. [D2I File Format -- Shared Stash](#4-d2i-file-format----shared-stash)
5. [Item Binary Format](#5-item-binary-format)
   - [5.1 Item Header / Simple Item Data](#51-item-header--simple-item-data)
   - [5.2 Huffman-Encoded Item Codes (D2R)](#52-huffman-encoded-item-codes-d2r)
   - [5.3 Extended Item Data](#53-extended-item-data)
   - [5.4 Quality-Specific Data](#54-quality-specific-data)
   - [5.5 Item-Specific Data (Armor, Weapons, Stacks)](#55-item-specific-data-armor-weapons-stacks)
   - [5.6 Magical Properties (Stat Lists)](#56-magical-properties-stat-lists)
   - [5.7 Set Bonus Properties](#57-set-bonus-properties)
   - [5.8 Runeword Properties](#58-runeword-properties)
6. [ItemStatCost.txt Reference](#6-itemstatcosttxt-reference)
7. [Checksum Algorithm](#7-checksum-algorithm)
8. [Unverified Fields](#8-unverified-fields)
9. [Source References](#9-source-references)

---

## 1. Version History and Save File Versions

The `.d2s` file version is stored as a `uint32` at byte offset 4.

| Version ID | Game Version | Key Changes | Status |
|-----------|-------------|-------------|--------|
| 71 (0x47) | v1.00 -- v1.06 | Original format | [VERIFIED] |
| 87 (0x57) | v1.07 / Expansion v1.08 | Expansion support added | [VERIFIED] |
| 89 (0x59) | Standard v1.08 | -- | [VERIFIED] |
| 92 (0x5C) | v1.09 | Major format overhaul, bit-packed items | [VERIFIED] |
| 96 (0x60) | v1.10 -- v1.14d | Last classic LoD format | [VERIFIED] |
| 97 (0x61) | D2R v1.0 -- v2.5 | Huffman-encoded item codes, no per-item JM header, stat bit widths changed | [VERIFIED] |
| 98 (0x62) | D2R v2.6+ | UTF-8 character names, extended appearance block, 128-bit online GUID | [PARTIAL] |
| 105 (0x69) | D2R v105 (Reign of the Warlock) | Warlock class, 833-byte header, shifted offsets | [VERIFIED] |

### D2R vs Classic Format -- Major Differences (v97+)

| Feature | Classic (v96 and below) | D2R (v97+) | Status |
|---------|------------------------|-----------|--------|
| Item header per item | `JM` (0x4A4D) prefix on every item | No per-item JM -- only on item list headers | [VERIFIED] |
| Item code encoding | 4x 8-bit ASCII chars at bit 76 | Huffman-encoded variable-length | [VERIFIED] |
| Stat bit widths (character) | Various (see v1.09 docs) | Changed -- see Section 3.5 | [VERIFIED] |
| Character name encoding | 7-bit ASCII | v97: partial UTF-8; v98+: full UTF-8 | [PARTIAL] |
| DWORD before quest data | 0 | 1 | [VERIFIED] |
| Socketed item count (simple items) | 3 bits | 1 bit for simple items | [VERIFIED] |

---

## 2. General Binary Conventions

| Convention | Details | Status |
|-----------|---------|--------|
| Byte order | Little-endian (x86 native) | [VERIFIED] |
| Bit reading order | LSB-first within bytes; bit fields span byte boundaries | [VERIFIED] |
| String encoding | Null-terminated, padded with 0x00 | [VERIFIED] |
| Fixed-point values | Life/Mana/Stamina use 8-bit fractional part (divide by 256 for display) | [VERIFIED] |

Bits are read LSB-first. To read an arbitrary bit field starting at bit offset N: locate byte N/8, shift right by N%8, and mask to the desired width. Multi-byte fields span naturally across byte boundaries.

---

## 3. D2S File Format -- Character Save

### 3.1 Header (833 bytes)

In D2R v105, the header is **833 bytes** (not 765 as in earlier versions). The extended header includes a 48-byte appearance extension and a 128-bit online GUID (was 96-bit in v97). All offsets below are for v105.

| Offset | Size | Description | Notes | Status |
|--------|------|-------------|-------|--------|
| 0x00 | 4 | Signature | Must be 0xAA55AA55 | [VERIFIED] |
| 0x04 | 4 | Version ID | 105 (0x69) for v105 | [VERIFIED] |
| 0x08 | 4 | File size | Total file size in bytes | [VERIFIED] |
| 0x0C | 4 | Checksum | See Section 7 | [VERIFIED] |
| 0x10 | 4 | Active weapon | 0 or 1 indicating weapon swap set | [VERIFIED] |
| 0x14 | 1 | Status byte | See Character Status Bits below | [VERIFIED] |
| 0x15 | 1 | Progression | 0=no title, 5=Normal, 10=NM, 15=Hell | [VERIFIED] |
| 0x18 | 1 | Character class | 0=Amazon .. 6=Assassin, 7=Warlock | [VERIFIED] |
| 0x1B | 1 | Level | Display level (must match stats section) | [VERIFIED] |
| **0x20** | **4** | **Last Saved timestamp** | **uint32 UNIX timestamp. MUST be updated on every write - game rejects stale values ('Failed to join Game').** | **[VERIFIED TC66]** |
| 0x12B | 16 | Character name | Null-terminated UTF-8 | [VERIFIED] |

> **NOTE:** The offsets above differ significantly from pre-v105 documentation. In particular, character name is at 0x12B (not 0x14), class is at 0x18 (not 0x28), and level is at 0x1B (not 0x2B).

> **CRITICAL:** The timestamp at 0x20 is validated by the game engine. External tools that modify `.d2s` files **must** update this field to `int(time.time())` before recomputing the checksum. Failure to do so causes "Failed to join Game" even when all other data is correct. The writer's `patch_timestamp()` handles this automatically.

> **NOTE:** The full v105 header layout between the fields listed above contains quest data, waypoint data, NPC data, appearance blocks, hotkeys, difficulty bytes, mercenary fields, and reserved regions. Only the most commonly referenced fields are listed here; remaining header fields follow the same general structure as earlier versions but at shifted offsets.

#### Character Status Bits

| Bit | Description | Status |
|-----|------------|--------|
| 2 | Hardcore | [VERIFIED] |
| 3 | Has died (ever) | [VERIFIED] |
| 5 | Expansion character | [VERIFIED] |
| 6 | Ladder | [PARTIAL] |

#### Character Class IDs

| ID | Class | Status |
|----|-------|--------|
| 0 | Amazon | [VERIFIED] |
| 1 | Sorceress | [VERIFIED] |
| 2 | Necromancer | [VERIFIED] |
| 3 | Paladin | [VERIFIED] |
| 4 | Barbarian | [VERIFIED] |
| 5 | Druid | [VERIFIED] |
| 6 | Assassin | [VERIFIED] |
| 7 | Warlock | [VERIFIED] |

#### Mercenary Header (14 bytes at 0xA1)

The mercenary **header** is a fixed 14-byte block inside the main D2S
header area - **independent from the mercenary item list**, which lives
much later in the file inside the `"jf"` section (see 3.9). This block
describes *who* the merc is; Section 3.9 describes *what the merc is
carrying*.

| Offset | Size | Field            | Notes |
|-------:|-----:|------------------|-------|
| 0xA1   | 2    | merc_dead        | 0=alive, 1=permadead (Hardcore) |
| 0xA3   | 4    | merc_control     | Random control seed. Non-zero for any hired merc. |
| 0xA7   | 2    | merc_name_id     | Index into the per-class merc-name list. |
| 0xA9   | 2    | merc_type        | Row index into hireling.txt. |
| 0xAB   | 4    | merc_experience  | Total experience points. |

**No merc hired:** all 14 bytes are zero. The control seed is a 32-bit
random integer for every real merc, so `control_seed == 0` is a safe
discriminator.

**Merc name resolution** uses the `NameFirst` template from hireling.txt
plus the stored `name_id`. Templates currently in use (D2R v105 +
Reimagined):

| Hireling class    | NameFirst..NameLast | Name key pattern |
|-------------------|---------------------|------------------|
| Rogue Scout       | merc01..merc41      | `merc{N:02d}` |
| Desert Mercenary  | merca201..merca221  | `merca2{N:02d}` |
| Eastern Sorceror* | merca222..merca241  | `merca2{N:02d}` |
| Barbarian         | MercX101..MercX167  | `MercX{N:03d}` |

\* "Eastern Sorceror" is the hireling.txt label for the Act 3 Iron
Wolf merc (Blizzard typo preserved).

The final localized string is looked up in
`data/local/lng/strings/mercenaries.json` (CASC) by the computed key.
Example: type=0 (Rogue Scout base row), name_id=5 -> `"merc01"` +
offset 5 -> `merc06` -> **"Paige"**.

Status: [BINARY_VERIFIED v105 Knurpsi/MrLockhart/AAAAA/FrozenOrbHydra/VikingBarbie + TC01/TC08/TC18/TC41/TC62 all-zero block]

### 3.2 Quest Data

Starts with header `"Woo!"` followed by 6 bytes (always `{06, 00, 00, 00, 2A, 01}`).

The quest data consists of 3 identical structures (Normal/Nightmare/Hell), each 96 bytes. Each quest is a 16-bit field where individual bits track quest progress milestones.

Status: [VERIFIED] for structure; individual quest bits are well-documented in legacy references.

### 3.3 Waypoint Data

Starts with header `"WS"` followed by 6 unknown bytes.

Three structures (one per difficulty), each 24 bytes:
- 2 bytes: always `{0x02, 0x01}`
- 5 bytes: waypoint bitfield (LSB order, 39 waypoints total)
- 17 bytes: unknown

Status: [VERIFIED]

### 3.4 NPC Data

Starts with header `"w4"`. Contains NPC introduction flags per difficulty.

Status: [PARTIAL]

### 3.5 Character Attributes / Stats

Starts immediately after the fixed header with the 2-byte header `"gf"`.

The stats section uses a **9-bit ID** followed by a **variable-length value**. The section is terminated by the 9-bit value 0x1FF (511 = all bits set).

**IMPORTANT:** Bit-reversal is NOT required for this section. Bits are read plain LSB-first, same as all other sections. Earlier documentation (notably nokka/d2s) incorrectly stated that bits must be reversed. This has been confirmed incorrect through binary verification.

#### Stat IDs and Bit Lengths (D2R v97+)

| ID | Stat | Bit Length | Notes | Status |
|----|------|-----------|-------|--------|
| 0 | Strength | 10 | Changed from 7 in v1.09 | [VERIFIED] |
| 1 | Energy | 10 | Changed from 7 | [VERIFIED] |
| 2 | Dexterity | 10 | Changed from 7 | [VERIFIED] |
| 3 | Vitality | 10 | Changed from 7 | [VERIFIED] |
| 4 | Stat points remaining | 10 | Changed from 9 | [VERIFIED] |
| 5 | Skill choices remaining | 8 | Same as before | [VERIFIED] |
| 6 | Current HP | 21 | Fixed-point (divide by 256) | [VERIFIED] |
| 7 | Max HP | 21 | Fixed-point (divide by 256) | [VERIFIED] |
| 8 | Current Mana | 21 | Fixed-point (divide by 256) | [VERIFIED] |
| 9 | Max Mana | 21 | Fixed-point (divide by 256) | [VERIFIED] |
| 10 | Current Stamina | 21 | Fixed-point (divide by 256) | [VERIFIED] |
| 11 | Max Stamina | 21 | Fixed-point (divide by 256) | [VERIFIED] |
| 12 | Level | 7 | -- | [VERIFIED] |
| 13 | Experience | 32 | -- | [VERIFIED] |
| 14 | Gold (inventory) | 25 | -- | [VERIFIED] |
| 15 | Gold (stash) | 25 | -- | [VERIFIED] |

These widths are defined by the `CSvBits` column in ItemStatCost.txt.

### 3.6 Skills

Immediately follows the stats section:
- 2-byte header: `"if"`
- 30 bytes: one byte per skill, representing allocated skill points

Skill offset per class:

| Class | Skill Offset | Status |
|-------|-------------|--------|
| Amazon | 6 | [VERIFIED] |
| Sorceress | 36 | [VERIFIED] |
| Necromancer | 66 | [VERIFIED] |
| Paladin | 96 | [VERIFIED] |
| Barbarian | 126 | [VERIFIED] |
| Druid | 221 | [VERIFIED] |
| Assassin | 251 | [VERIFIED] |
| Warlock | Unknown | [UNVERIFIED] |

### 3.7 Item Lists

Immediately follows the skills section.

#### Item List Header

| Size | Description | Status |
|------|------------|--------|
| 2 bytes | `"JM"` header (0x4A, 0x4D) | [VERIFIED] |
| 2 bytes (uint16) | Item count (**root items only** - `location_id != 6`) | [VERIFIED] |

After the header come N root items in sequence. Each item's bit length is variable (see Section 5). Socket children (`location_id == 6`) follow their parent in the byte stream but are NOT counted in the JM header - the game discovers them via the parent's `total_nr_of_sockets` field.

**Verified (TC67 GAME-written):** 16 root items + 4 socket children = 20 flat items, JM=**16** (not 20). [BV CubeContents.d2s]

**For writers:** `jm_count = len(root_items)`. Simple, and survives mutations.

After the player's item list, there is a second `"JM"` + uint16 header for corpse data (see 3.8).

### 3.8 Corpse Data

If the character has died, the second item list contains corpse item data:
- 16-byte corpse header
- Standard item list (same format as player items)

Status: [PARTIAL]

### 3.9 Mercenary Item Section (`"jf"`, Expansion)

After corpse data, expansion characters have a mercenary **item list**
section. This is physically distinct from the merc **header** block at
0xA1 (see 3.1 "Mercenary Header"): the 0xA1 block says *who* the merc
is, this section lists *what they carry*.

Layout:
- 2-byte header: `"jf"`
- If mercenary exists (alive or dead): standard item list header
  (`"JM"` + uint16 count) + items
- 2-byte trailer: `"kf"`

Socket children of merc-equipped items are stored inline after their
parent, exactly as in the player item list (Section 3.7).

#### Reimagined merc slot extension

Vanilla D2 mercs can only equip head, body, and a weapon (Act 5
Barbarian mercs sometimes also a shield). **D2R Reimagined extends
merc paperdolls to all 10 hero slots**: Head, Amulet, Body Armor,
Right Hand (weapon), Left Hand (shield or quiver - empty when the
weapon is 2H), Right Ring, Left Ring, Belt, Boots, Gloves. The parser
does not enforce slot restrictions on the merc item list, so this
works out of the box.

Status: [VERIFIED v105 Reimagined, user-confirmed Knurpsi/MercOnly]

### 3.10 Iron Golem (Necromancer, Expansion)

After the `"kf"` marker:
- 1 byte: has_golem (0 or 1)
- If 1: a single item structure follows

Status: [PARTIAL]

---

## 4. D2I File Format -- Shared Stash

The `.d2i` file is D2R's shared stash format. It has no file-level header, no checksum, and no character data.

### Section Structure

The D2I file contains **7 sections**: 6 JM-delimited item lists followed by 1 block of trailing metadata.

| Section | JM Header | Type | Description |
|---------|-----------|------|-------------|
| 0 | Yes | Grid tab (16x13) | Shared Stash Tab 1 |
| 1 | Yes | Grid tab (16x13) | Shared Stash Tab 2 |
| 2 | Yes | Grid tab (16x13) | Shared Stash Tab 3 |
| 3 | Yes | Grid tab (16x13) | Shared Stash Tab 4 |
| 4 | Yes | Grid tab (16x13) | Shared Stash Tab 5 |
| 5 | Yes | Special: Gems/Materials/Runes | No grid, quantity-based (0-99 per entry) |
| 6 | No | Trailing metadata | 148 bytes, game-internal tracking data |

Each of sections 0-5 begins with a **64-byte section header** (signature `0xAA55AA55`, version, `section_size` at header offset 0x10), followed by the standard item list header (`"JM"` + uint16 count), followed by items in standard binary format.

> **CRITICAL (section boundary):** Each section is self-contained - its
> `section_size` field defines the exact byte extent. Parsers and writers
> MUST NOT read or write item data past the section boundary. The last
> item in a grid tab can overshoot into the next section's 64-byte header
> during property/set-bonus parsing if the boundary is not enforced. The
> parser's `section_end_byte` clamp and the writer's byte-splice approach
> both guard against this. [BINARY_VERIFIED TC66: Immortal King's Cage
> at the end of tab 0 had 20 bytes of tab-1's header baked into its
> source_data before the fix.]

#### Grid Tabs (Sections 0-4)

Standard grid layout. Items have grid positions (position_x, position_y) and use panel_id=5 for shared stash.

D2I grid tabs store items in **two regions**:

1. **JM-counted items** - the uint16 after the JM marker counts only
   **root items** (location_id != 6). Socket children follow their
   parent in the byte stream but are NOT included in the JM count.
   The game discovers children via the parent's socket count field.
   [BV TC67: adding a 4-socket runeword increases JM by 1, not 5.]
2. **Extra items** - additional items stored AFTER the JM-counted
   region in the same section, without their own JM count. These are
   regular stash items (location_id=0, NOT socket children) that the
   game writes past the JM boundary for reasons not fully understood.
   [BV: Tab 3 has 28 JM items + 16 extra items.]

> **Note:** Writers must use byte-splicing (not full rebuild) when
> modifying grid tabs. ``tab.items`` contains only root items (socket
> children live in ``ParsedItem.socket_children``). JM delta is simply
> ``len(new_items) - len(orig_items)``. Writers must clear D2S-only
> flags (bit 13) on all items written to D2I, and write each parent's
> socket children inline after the parent blob. Extra items beyond the
> JM boundary are preserved verbatim via ``original_tail``.

#### Special Tab (Section 5): Gems / Materials / Runes

Displayed in-game as 3 sub-tabs: Gems, Materials, Runes. Items in this section have no grid positions. Each entry can have a quantity of 0 to 99. Only specific item types are allowed: individual gems (not gem bags), worldstone shards, essences, individual runes, and rejuvenation potions (35% and full). Tomes, scrolls, healing/mana potions, and equipment cannot be stored in section 5.

#### Trailing Metadata (Section 6)

148 bytes with no JM marker. Contains game-internal tracking data (timestamps, session IDs). Updated by the game on every save.

#### Item Order

Items within each section are stored in **insertion order** (oldest first), not by grid position. This ordering must be preserved for write fidelity.

#### Version Dependency

The D2I file does not store a version number. The game version must be provided externally to correctly parse items (Huffman encoding, bit widths, etc.).

Status: [VERIFIED]

---

## 5. Item Binary Format

### 5.1 Item Header / Simple Item Data

In D2R (v97+), individual items do NOT have a `"JM"` prefix. Only item list headers have `"JM"`. In classic (v96 and below), every item starts with `"JM"`.

#### D2R Item Bit Layout (v97+)

| Bit Offset | Size | Description | Status |
|-----------|------|-------------|--------|
| 0 | 4 | Unknown | [VERIFIED] |
| 4 | 1 | Identified | [VERIFIED] |
| 5 | 6 | Unknown | [VERIFIED] |
| 11 | 1 | Socketed | [VERIFIED] |
| 12 | 1 | Unknown | [UNVERIFIED] |
| 13 | 1 | Picked up since last save (D2S only, always 0 in D2I) | [VERIFIED] |
| 14 | 2 | Unknown | [UNVERIFIED] |
| 16 | 1 | Is Ear | [VERIFIED] |
| 17 | 1 | Starter item | [VERIFIED] |
| 18 | 3 | Unknown | [UNVERIFIED] |
| 21 | 1 | Simple (compact) item | [VERIFIED] |
| 22 | 1 | Ethereal | [VERIFIED] |
| 23 | 1 | Unknown (often 1) | [UNVERIFIED] |
| 24 | 1 | Personalized | [VERIFIED] |
| 25 | 1 | Unknown | [UNVERIFIED] |
| 26 | 1 | Runeword | [VERIFIED] |
| 27 | 5 | Unknown | [UNVERIFIED] |
| 32 | 8 | Item version | [PARTIAL] |
| 35-37 | 3 | Location ID (stored/equipped/belt/cursor/socket) | [VERIFIED] |
| 42-49 | varies | Equipped slot / position fields | [VERIFIED] |
| 50-52 | 3 | Panel (inventory/cube/stash) | [VERIFIED] |
| 53+ | varies | Huffman-encoded item code (see 5.2) | [VERIFIED] |

> NOTE: The Huffman-encoded item code begins at bit 53. Bit offsets above are for D2R (v97+), without the classic JM prefix.

After the Huffman-decoded item code, for simple items, the next field is the socketed item count (1 bit for D2R simple items, 3 bits for extended items). If the item is simple (bit 21 set) and not stackable, the item ends here.

If the simple item is stackable (per `stackable` column in weapons.txt/misc.txt), a 9-bit quantity field follows the socket bit.

#### Simple Item Quantity Encoding

The 9-bit quantity field for simple items has a special encoding:

```
  Bit 0:   alignment/flag bit (always 1 in D2R v105)
  Bits 1-8: display quantity (the value the player sees in-game)
```

The raw stored value equals `(display_quantity << 1) | 1`. To recover
the display quantity: `display = raw >> 1`.

Examples (binary-verified against in-game values):

| Item | Raw (9 bits) | Raw binary | Display | Formula |
|------|-------------|------------|---------|---------|
| r10 (64 stacked) | 129 | 010000001 | 64 | 129 >> 1 = 64 |
| rvs (85 stacked) | 171 | 010101011 | 85 | 171 >> 1 = 85 |
| r08 (72 stacked) | 145 | 010010001 | 72 | 145 >> 1 = 72 |
| r09 (35 stacked) | 71 | 001000111 | 35 | 71 >> 1 = 35 |

Extended (non-simple) stackable items use a 7-bit field that stores
the display value directly - no shift needed.

Status: [BINARY_VERIFIED 42 simple items, 2 cross-verified against in-game display]

#### Simple Item Trailing Padding

After the final field (socket bit, or 9-bit quantity for stackables), simple items are padded to the next byte boundary. **The minimum padding is 1 bit, not 0.** When the running bit count is already byte-aligned, a full trailing padding byte (8 bits, always zero) is still present in the binary.

This matters for items whose Huffman code length produces an exact-byte sum:

| Code(s) | Huffman bits | 53 + h + 1 | Real binary size |
|---------|-------------|------------|------------------|
| hp2, mp2 | 18 | 72 (byte-aligned) | **80 bits (10 bytes)** |
| hp1, hp3, mp1, mp3 | 19 | 73 | 80 bits (10 bytes) |
| hp4, hp5, mp4, mp5 | 20 | 74 | 80 bits (10 bytes) |
| mss | 15 | 69 | 72 bits (9 bytes) |
| rvs (quantity) | 18 | 72 + 9 = 81 | 88 bits (11 bytes) |
| rvl (quantity) | 19 | 73 + 9 = 82 | 88 bits (11 bytes) |

A naïve "round current bit position up to the nearest byte" is wrong for
hp2/mp2: it produces 72 bits where the real size is 80. The correct rule
is "round to the next byte boundary AND advance at least 1 bit". In
practice the parser probes forward 8/16/24 bits for a valid Huffman code
after each simple item to detect the real next-item offset.

Status: [VERIFIED TC62]

### 5.2 Huffman-Encoded Item Codes (D2R)

In D2R, item type codes are encoded using a Huffman tree instead of plain 4-character ASCII.

#### Huffman Code Table

Each character of the item code is encoded with a variable-length bit pattern (read LSB-first):

```
' ' (space/terminator) -> 10
'0' -> 11111011      '1' -> 1111100       '2' -> 001100
'3' -> 1101101       '4' -> 11111010      '5' -> 00010110
'6' -> 1101111       '7' -> 01111         '8' -> 000100
'9' -> 01110         'a' -> 11110         'b' -> 0101
'c' -> 01000         'd' -> 110001        'e' -> 110000
'f' -> 010011        'g' -> 11010         'h' -> 00011
'i' -> 1111110       'j' -> 000101110     'k' -> 010010
'l' -> 11101         'm' -> 01101         'n' -> 001101
'o' -> 1111111       'p' -> 11001         'q' -> 11011001
'r' -> 11100         's' -> 0010          't' -> 01100
'u' -> 00001         'v' -> 1101110       'w' -> 00000
'x' -> 00111         'y' -> 0001010       'z' -> 11011000
```

The item code is terminated by a space character (`' '` -> `10`). Codes are 3-4 characters long (e.g., `"amu"` for Amulet, `"r01"` for El Rune).

Status: [VERIFIED]

### 5.3 Extended Item Data

If the item is NOT simple, additional data follows the item code:

| Field | Size | Description | Status |
|-------|------|-------------|--------|
| Socket count (filled) | 3 bits | Number of gems/runes currently in sockets | [VERIFIED] |
| unique_item_id | 35 bits | Random anti-dupe identifier. **MUST be distinct across all items in a save file** - D2R rejects files with duplicate UIDs. Writers must guarantee uniqueness (the toolkit's `ensure_unique_uids()` does this automatically). | [BV] |
| Item level | 7 bits | Drop/creation level | [VERIFIED] |
| Quality | 4 bits | See Section 5.4 | [VERIFIED] |
| Has custom graphics | 1 bit | If set, graphic fields follow | [VERIFIED] |
| Graphic index | 3 bits | Only if has_custom_graphics=1 | [VERIFIED] |
| GFX extra | 1 bit | Only if has_custom_graphics=1. D2R v105 specific. Creates a carry-chain that shifts QSD fields by 1 bit. | [VERIFIED] |
| Has class data | 1 bit | Automod flag | [VERIFIED] |
| Class data (automod) | 11 bits | Index into automagic.txt. See presence rules below. | [VERIFIED] |

#### GFX Extra Bit

This 1-bit field is present only when has_custom_graphics=1. It creates a carry-chain effect where the has_class bit and all subsequent quality-specific data values are shifted by 1 bit position. Quality-specific compensation formulas are required (see Section 5.4).

This bit is not documented in earlier format references.

#### Automod (Class Data) Presence Rules

The 11-bit automod field is NOT always present when has_class=1. Presence is decided by two orthogonal properties of the item row in weapons.txt / armor.txt / misc.txt:

- **`auto prefix`** column (non-empty value vs empty): controls whether the engine rolls a random automod on creation.
- **`bitfield1`** column (bf1, bit 0 set vs clear): controls how the automod slot is gated in the binary.

The resulting presence rules:

| Row in txt | Category | bitfield1 | When Automod is Read |
|------------|----------|-----------|---------------------|
| `auto prefix` set, bf1=True | Armor, weapons (most), shields (all), class helms, paladin auric shields | True | Only when has_class=1 |
| `auto prefix` set, bf1=False | Charms, tools, orbs | False | Always (except Unique quality q=7) |
| `auto prefix` **empty**, bf1=True | **`crs`** (only weapon), generic belts/boots/circlets/gloves/generic helms (cap, skp, hlm, fhl)/pelts/primal helms/generic torsos (qui, lea, hla, stu, brs, ...) | True | **Only when has_class=1** (same as the first row - the `auto prefix` value only controls whether the slot is *randomly filled*, not whether it exists) |
| `auto prefix` empty, bf1=True | Jewels, rings, amulets (MISC category) | True | Never - has_class flows into the carry-chain instead, shifting QSD fields by 1 bit |

Critical distinction: the third and fourth rows both have empty `auto prefix`, but the behaviour differs by **item category**. WEAPON and ARMOR still reserve the 11-bit slot whenever has_class=1; MISC jewels/rings/amulets do not (their has_class bit is absorbed into the quality-specific-data carry-chain - see Section 5.4 formulas).

Status: [VERIFIED TC63]

#### After Extended Header: Runeword + Personalization + Timestamp

```
if runeword_flag (bit 26):
    runeword_id    = read 12 bits   // row index into runes.txt
    rw_unknown     = read 4 bits

if personalized_flag (bit 24):
    name = read null-terminated string (7-bit chars, max 15)

timestamp = read 1 bit              // ALWAYS present for all extended items
```

The timestamp bit is always 1 bit and always present for all extended items, regardless of has_gfx or any other flag.

### 5.4 Quality-Specific Data

The 4-bit quality field determines what follows. For has_gfx=1 items, the gfx_extra carry-chain shifts all values by 1 bit -- compensation formulas are noted.

| Quality ID | Name | Additional Data | Carry-Chain Formula (has_gfx=1) |
|-----------|------|----------------|-------------------------------|
| 1 | Low Quality | 3 bits: quality type | -- |
| 2 | Normal | No additional data | -- |
| 3 | Superior | 3 bits: superior type | -- |
| 4 | Magic | 11 bits prefix + 11 bits suffix (0=none) | prefix = (has_class \| (raw<<1)) - 1 |
| 5 | Set | 12 bits: set ID | *ID = raw*2 + has_class |
| 6 | Rare | 8+8 name IDs + 6x(1+opt 11-bit affix) | name1 = (has_class \| (raw<<1)) - 156 |
| 7 | Unique | 35 bits: unique_item_id | *ID = binary_to_star_id(uid * 2 + has_class) |
| 8 | Crafted | Same as Rare format | Same as Rare |

> NOTE: The unique_item_id field is 35 bits wide (not 32). The binary_to_star_id() conversion is necessary because D2R Reimagined adds separator rows in UniqueItems.txt that cause the binary UID to differ from the *ID column.

Status: [VERIFIED]

#### Rare / Crafted Affix Structure

After the two 8-bit name IDs, there are 6 standard affix slots. Each slot N is pre-assigned to a specific table: even slots (0, 2, 4) index into `magicprefix.txt`, odd slots (1, 3, 5) index into `magicsuffix.txt`. A slot's assignment does **not** shift when earlier slots are empty - the slot number is the row-index source of truth for the table lookup.

```
for slot in 0..5:
    has_affix = read 1 bit
    if has_affix:
        affix_id = read 11 bits
        # slot is PREFIX if slot % 2 == 0, else SUFFIX
```

**D2R v105 extension for non-stackable MISC items:** Rare/Crafted jewels, charms, and similar non-stackable MISC items may have a **7th affix slot** with a 10-bit ID (not 11):

```
has_7th_affix = read 1 bit
if has_7th_affix:
    affix_id = read 10 bits
    # slot 6 is a PREFIX (even)
```

Parsers that store affixes as a compact "filled slots only" list must keep a parallel list of slot indices; the slot position is **not** recoverable from enumeration order because empty slots are skipped. See `ParsedItem.rare_affix_ids` and `ParsedItem.rare_affix_slots` in this toolkit's implementation.

Status: [VERIFIED]

#### Rare/Crafted Required Level Formula

For **Rare** items (quality=6) the required level is simply:

```
required_level = max(affix_lvlreq for each rolled affix)
```

For **Crafted** items (quality=8) the formula includes a recipe-mandated layer on top of the rolled affixes:

```
required_level = max_affix_lvlreq + 10 + 3 * num_affixes
```

Ground truth - FrozenOrbHydra inventory, all 4 Grand Charms (2026-04-14):

| Charm | ilvl | n_affixes | max_affix_lvlreq | formula | in-game |
|-------|-----:|----------:|-----------------:|--------:|--------:|
| Ghoul Eye | 60 | 3 | 40 | 40 + 10 + 9 | 59 |
| Grim Eye  | 80 | 4 | 70 | 70 + 10 + 12 | 92 |
| Doom Eye  | 60 | 4 | 42 | 42 + 10 + 12 | 64 |
| Dread Eye | 60 | 3 | 42 | 42 + 10 + 9 | 61 |

`ilvl` does not appear in the formula - the value is pure affix-driven. The +10 is a fixed crafting overhead; the +3·n scales with the count of rolled affixes to account for the recipe bonus layer. Applying the formula to Rare items would inflate their required level by 10-28 levels; the quality=8 gate is mandatory.

Status: [VERIFIED, FrozenOrbHydra]

#### Rare/Crafted Name ID Offsets

Name IDs use a unified namespace. The raw 8-bit values require offset adjustments:
- name_id1 (prefix): subtract 156 from raw value
- name_id2 (suffix): subtract 1 from raw value

For has_gfx=1 items, the carry-chain formulas in the table above apply instead.

#### Rare/Crafted Name Display Resolution

The adjusted `name_id1` / `name_id2` index into `rareprefix.txt` / `raresuffix.txt`. The `name` column in those tables is a **string-table key**, not display text - it must be resolved through the same `StringsDatabase` (`item-nameaffixes.json`, `item-names.json`, ...) that handles magic prefix/suffix lookups.

For most rows the key coincides with the enUS display text ("Beast" -> "Beast"), which is why raw-key passthroughs worked historically. In Reimagined however ~160 rows have divergent keys:

| Raw key in .txt | enUS display |
|-----------------|--------------|
| `GhoulRI` | `Ghoul` |
| `PlagueRI` | `Plague` |
| `Wraithra` | `Wraith` |
| `Fiendra` | `Fiend` |
| `Empyrion` | `Empyrian` |
| `Holocaust` | `Armageddon` |
| `bite`, `fang`, `razor`, ... (lowercase) | `Bite`, `Fang`, `Razor`, ... |

Implementations that skip the string-table lookup will render the first six as `Ghoulri`, `Plagueri`, `Wraithra`, `Fiendra`, `Empyrion`, `Holocaust` and the lowercase-suffix group as `Bite`-cased-lowercase, all of which mismatch the in-game tooltip. Fallback to `key.capitalize()` is only appropriate when the strings database has no entry for the key.

Status: [VERIFIED against in-game tooltip, FrozenOrbHydra.d2s]

### 5.5 Item-Specific Data (Armor, Weapons, Stacks)

After quality-specific data, type-specific fields depend on the item category from armor.txt/weapons.txt/misc.txt.

#### Armor

```
defense          = read 11 bits      // subtract Save Add (10) for display value
max_dur          = read 8 bits
cur_dur          = read 8 bits       // always present for armor (see invariant below)
unknown_post_dur = read 2 bits
```

Durability is 8+8 bits (not 9+9 as in some older documentation).

**Invariant** - in the D2R binary layout, ``max_dur == 0`` would in
principle be the sentinel for "no durability block", with ``cur_dur``
omitted (the same rule weapons use - see *Weapons* below).  Every
armor row in Reimagined 3.0.7 armor.txt has ``durability > 0`` (0 of
218 rows trip the sentinel), so the parser always reads the full
18-bit block.  The in-game "Indestructible" property is instead
encoded via stat 152 (``item_indesctructible = 1``) on top of a
normal durability value; it does NOT use the ``max_dur = 0``
sentinel for armor.  If a future mod update adds a ``durability=0``
armor row, the parser must be extended with the same
``if max_dur > 0`` gating the weapon branch uses (see
``has_durability_bits`` in ``ItemTypeDatabase``).

Status: [BINARY_VERIFIED - all armor in Reimagined 3.0.7 has durability > 0]

#### Weapons

```
max_dur = read 8 bits
if max_dur > 0:
    cur_dur          = read 8 bits
    unknown_post_dur = read 2 bits                 // 18-bit block
else:
    unknown_post_dur = read 1 bit                  //  9-bit block
```

The ``unknown_post_dur`` field width is variable - **2 bits when
``cur_dur`` is present, 1 bit when omitted**.  This is the core rule
that distinguishes weapons from armor.  The sole reliable predicate
is the runtime ``max_dur`` value: weapons with ``max_dur == 0`` in
the binary carry a single trailing bit and then jump straight into
the ISC property stream.

In D2R Reimagined 3.0.7 this branch is exercised by exactly **one**
weapon: Phase Blade (``7cr``), the only weapon row in weapons.txt
with ``durability=0``.  Every other weapon - including every bow /
crossbow that sets ``nodurability=1`` - still carries
``durability=250`` and therefore uses the standard 18-bit layout.
Callers that want a pre-parse answer can consult
``ItemTypeDatabase.has_durability_bits(code)``.

The canonical user-visible fix case was **Lightsabre** (unique
Phase Blade, ``*ID=259``), which before the variable-width rule
surfaced as a 10-bit drift on every downstream ISC stat
(fire_dam=2 930 752, cold_dam=3 945 929, Adds 19-0 Weapon Damage,
+3 686 540% Enhanced Defense, ...).  See
``tests/test_phase_blade_durability.py`` for the 46-check
regression matrix, pinned against TC56/VikingBarbie's untampered
copy of the item.

Status: [BINARY_VERIFIED TC56/Lightsabre + TC09/TC33 bow sweep]

#### Socketed Armor Layout

After the base armor/weapon fields:

```
unknown_post_dur = read 2 bits

if socketed:
    if shield AND NOT runeword AND quality != 7 (Unique):
        shield_unknown = read 2 bits

    if shield AND runeword:
        sock_count     = read 4 bits
        rw_data        = read 24 bits       // 28 bits total
    elif quality == 3 (Superior) AND NOT runeword:
        sock_unknown   = read 20 bits       // 4 count + 16 quality data
        sock_count     = sock_unknown & 0xF
    else:
        sock_count     = read 4 bits

if quality == 5 (Set):
    set_bonus_mask = read 5 bits
```

Key rules for socket field widths:
- **shield_unknown(2)**: Only for non-RW, non-Unique shields. Unique shields do NOT have this field.
- **RW shields**: 28 bits total (4 socket count + 24 RW data), no shield_unknown.
- **Superior non-RW**: 20 bits (4 socket count + 16 quality data).
- **All others** (Normal, Magic, Rare, Set, Unique, Crafted, non-shield RW): just 4 bits for socket count.

Status: [VERIFIED]

#### Stackable Items (Quantity)

If item is stackable (from weapons.txt/misc.txt `stackable` column):
- **Simple items**: 9 bits - bit 0 is an alignment/flag (always 1),
  bits 1-8 carry the display value. See Section 5.1 for the encoding.
- **Extended items**: 7 bits - direct display value (no shift needed).
  Used for Section 5 advanced-stash stackables (keys, shards, statues).

Status: [BINARY_VERIFIED]

#### Tome Extra Field

Tomes have an extra 5 bits inserted before quantity.

Status: [PARTIAL]

#### Inter-Item Byte Alignment

Each item in the binary stream is **byte-aligned**: after the last bit of
the item's data, the reader advances to the next byte boundary (0-7 bits
of zero-padding). The next item starts at that byte.

For **extended** items, the last data is the final 0x1FF terminator of
the last property list (base properties, or set bonus lists, or runeword
properties - whichever comes last). There is **NO byte-alignment between
property lists** - only at the very end of the entire item.

For **simple** items, see *Simple Item Trailing Padding* in Section 5.1.

> **IMPORTANT (2026-04-13 fix):** The 3-59 byte "inter-item padding"
> reported in earlier versions was predominantly a parser bug: the
> "padding" bytes were Set bonus property lists and Runeword property
> lists that the parser failed to read due to a false byte-alignment
> step. With the alignment removed, D2I section gaps are 0 bytes.
> GoMule confirms: no alignment between property lists.

#### Set/Unique Inter-Item Padding (6-7 bytes)

**Set (quality=5) and Unique (quality=7) items** have 6-7 bytes (48-56
bits) of additional data between the item's byte-aligned end and the
next item's start. This padding is:

- **Exclusive to quality 5 and 7** - all other qualities have at most
  1 byte (byte-alignment). Verified across 2818 items in 86 save files.
- **Present in all categories**: ARMOR, WEAPON, and MISC.
- **Not correlated** with enchantment status, corruption status, or
  set_bonus_mask value.
- **Content unknown**: the bytes do not decode as ISC property lists
  (no 0x1FF terminators found), stat IDs, or any known field structure.
  Likely a D2R Reimagined mod extension (possibly enchantment/corruption
  slot metadata stored outside the property list).
- **Deterministic**: same item always produces the same padding bytes.
- **GoMule-confirmed**: GoMule D2R calculates the same item lengths
  as our parser (excluding the padding), confirming the bytes are not
  unread property data. GoMule-Reimagined cannot load current saves,
  possibly because it does not account for this padding.

Detection strategy: after parsing each item, probe forward at 8-bit
offsets (0, 8, ..., 56) for a valid Huffman code with a plausible
``location_id`` (0=STORED, 1=EQUIPPED, 6=SOCKETED). The padding bytes
are appended to the item's ``source_data`` so the D2I/D2S writers
preserve them. Ghost items (invalid Huffman codes from padding bytes
at section boundaries) are detected and merged back.

Status: [BINARY_VERIFIED 2026-04-13, 2818 items, 0 parse errors]

### 5.6 Magical Properties (Stat Lists)

After all item-specific data, magical properties are stored as a list of stat entries terminated by 0x1FF (9 bits, all ones).

#### Reading Algorithm

```
loop:
    stat_id = read 9 bits
    if stat_id == 0x1FF (511):
        break

    Look up stat_id in ItemStatCost.txt:
        save_bits       = ISC[stat_id]["Save Bits"]
        save_add        = ISC[stat_id]["Save Add"]
        save_param_bits = ISC[stat_id]["Save Param Bits"]
        encode_type     = ISC[stat_id]["Encode"]

    if save_param_bits > 0:
        param = read save_param_bits bits

    switch encode_type:
        case 0 (default):
            value = read save_bits bits
            value = value - save_add

        case 1 (min-max pair):
            value1 = read save_bits bits
            value1 = value1 - save_add
            // Automatically read NEXT stat row
            value2 = read ISC[stat_id+1]["Save Bits"] bits
            value2 = value2 - ISC[stat_id+1]["Save Add"]

        case 2 (skill-on-event):
            level    = read 6 bits
            skill_id = read 10 bits
            chance   = read (save_bits - 16) bits

        case 3 (charged skill):
            level       = read 6 bits
            skill_id    = read 10 bits
            charges     = read 8 bits
            max_charges = read 8 bits
```

The `Save Bits`, `Save Add`, and `Save Param Bits` columns in ItemStatCost.txt define the encoding of every stat.

Status: [VERIFIED] for encode types 0-3.

#### Display-only notes: descfunc conditional templates

A handful of ISC stats use `descfunc` values that pick between two
localized templates based on the stored value. These require special
handling in any display layer:

- **descfunc=11** (`item_replenish_durability`, stat 252): picks
  between `ModStre9u` ("Repairs %d durability in %d seconds") and
  `ModStre9t` ("Repairs %d durability per second"). Rule:
  - `value <  100` -> `ModStre9u` with `(1, 100 // value)`.
  - `value >= 100` -> `ModStre9t` with `(value // 100)`.
  - Example: stored value=5 -> "Repairs 1 durability in 20 seconds".

#### Reimagined hidden stats

Reimagined introduces **skill 449 "Hidden Charm Passive"**, an invisible
passive that every weapon and every shield carries as a stat 97
`item_nonclassskill` entry with `param=449`. This stat must be:

- **Filtered from any user-visible display** - the user never sees it
  in-game, so rendering it would look like a parser bug.
- **Preserved in the raw property list** so D2S/D2I writers round-trip
  it back into the binary. Dropping it would corrupt the item on
  rebuild.

Normal oskill items (e.g. Iceblink's "+1 to Warp") also use stat 97,
but with a real skill ID as the param. Filter by `param ∈
HIDDEN_SKILL_PARAMS`, never by the stat_id alone.

### 5.7 Set Bonus Properties

If the item is a Set item (quality 5), a **5-bit bonus mask** is read
during item-specific data (after durability/sockets). For each bit set
(LSB first), an additional complete property list is read, each
terminated by its own 0x1FF.

> **CRITICAL:** The bonus property lists are read **immediately** after
> the base property list's 0x1FF terminator, with **NO byte-alignment**
> between them. The bit stream flows continuously:
>
> ```
> [base properties] -> 0x1FF -> [bonus list 1] -> 0x1FF -> [bonus list 2] -> 0x1FF -> ...
> ```
>
> Byte-alignment happens ONCE at the very end, after the last property
> list of the entire item. This was confirmed by GoMule analysis and
> binary verification on Set items where the base 0x1FF falls on a
> non-byte-aligned position (e.g. uhc Colossus Girdle, base ends at
> bit 281 = 35.125 bytes). [BINARY_VERIFIED 2026-04-13]

These are the item-specific set bonuses (triggered by wearing N pieces).
Global set bonuses (the set's overall bonuses) are NOT stored in the
item binary; they are defined in sets.txt and applied by the game engine
at runtime.

Status: [BINARY_VERIFIED 2026-04-13, 0-byte gaps across all D2I sections]

### 5.8 Runeword Properties

If the item has the runeword flag set (bit 26), after all other property lists there is one additional property list containing the runeword's display properties. This list uses the same format (stat entries terminated by 0x1FF).

Runeword display properties include stat 387 (item_nonclassskill_display) as a display mirror for granted skills.

The binary layout of a runeword item's properties is: `[internal state properties] + 0x1FF + [display properties] + 0x1FF`.

Status: [VERIFIED]

---

## 6. ItemStatCost.txt Reference

This file defines how every stat is encoded in save files.

### File Format

Tab-delimited text. The first row is the header row with column names. Each subsequent row defines one stat. The `*ID` column is the 9-bit stat identifier used in item property lists.

D2R Reimagined overrides this file with additional stats. The mod's version must be used, not the vanilla file.

### Key Columns for Binary Encoding

| Column | Description |
|--------|-------------|
| Stat | Stat name (string key) |
| *ID | Numeric stat ID (the 9-bit key in property lists) |
| Signed | Whether value is signed (if 1, interpret as signed integer) |
| Save Bits | Number of bits for the value in save files |
| Save Add | Bias to subtract from stored value |
| Save Param Bits | Number of bits for the parameter field (if >0, read before value) |
| Encode | Encoding type (0/1/2/3) -- determines multi-field layout |
| CSvBits | Character stat bit width (used for Section 3.5) |
| CSvParam | Character stat param bits |
| ValShift | Right-shift amount for display (typically 8 for per-level stats) |
| op | Operator type (for per-level/by-time stats) |
| op param | Operator parameter (divisor for per-level calculation) |

### Encoding Rules

**Encode Type 0 (Default):** Read `Save Bits` bits, subtract `Save Add`.

**Encode Type 1 (Min-Max Pair):** Read current stat's value, then automatically read the NEXT stat ID's value. Both stats share a single 9-bit header (only the first ID is stored). Example: `item_maxdamage_percent` (ID 17) with Encode=1 means it is paired with `item_mindamage_percent` (ID 18).

**Encode Type 2 (Skill-on-Event):** Total bits = `Save Bits`. Split as: 6 bits level, 10 bits skill ID, remaining bits chance percentage.

**Encode Type 3 (Charged Skill):** Total bits = `Save Bits`. Split as: 6 bits level, 10 bits skill ID, 8 bits current charges, 8 bits max charges.

### ISC Stat Count

D2R Reimagined defines exactly **436 stats** (IDs 0-435). No higher IDs exist in the mod's ItemStatCost.txt.

Status: [VERIFIED]

---

## 7. Checksum Algorithm

The checksum is stored at bytes 12-15 (offset 0x0C) as a uint32. Applies to .d2s files only; .d2i files have NO checksum.

### Algorithm

1. Set bytes 12-15 to zero
2. Initialize sum = 0 (32-bit unsigned)
3. For each byte in the file:
   a. sum = rotate_left(sum, 1) -- circular left rotation by 1 bit
   b. sum = sum + byte_value
4. Store result at bytes 12-15 (little-endian)

Status: [VERIFIED]

---

## 8. Unverified Fields

| Field | Section | Notes |
|-------|---------|-------|
| Iron Golem item | 3.10 | has_golem byte confirmed; item structure not yet verified |
| Personalization encoding in v105 | 5.3 | Whether personalized names use UTF-8 or 7-bit ASCII |
| Warlock skill offset | 3.6 | Not yet confirmed from skills.txt |
| Item header unknown bits | 5.1 | Bits 0-3, 5-10, 12, 14-15, 18-20, 23, 25, 27-31 (see table) |

Previously unverified, now verified:
- **Mercenary item list** (3.9): Fully verified TC49/TC55/TC56/TC63/TC64. Reimagined 10-slot paperdoll confirmed.
- **Mercenary header** (3.1): 14-byte block at 0xA1 fully mapped. Name resolution via mercenaries.json.
- **Last-saved timestamp** (3.1): uint32 LE at 0x20. Game rejects stale values.
- **D2I section boundaries** (4): Section-size field at header+0x10 verified. Parser clamps source_data.
- **Simple item quantity encoding** (5.1): Bit 0 = flag (always 1), display = raw >> 1. 42 items verified.
- **Inter-item padding content** (5.5): The 3-59 byte padding was predominantly Set bonus / Runeword property lists the parser failed to read (fixed). Remaining: Set (q=5) and Unique (q=7) items have 6-7 bytes of real inter-item padding with unknown content (likely Reimagined mod extension). 2818 items verified across 86 save files, 0 parse errors.
- **Set bonus property list alignment** (5.7): No byte-alignment between property lists. Bit stream flows continuously. Verified via GoMule analysis + binary proof on non-byte-aligned Set items.

---

## 9. Source References

| Source | Type | Coverage | URL |
|--------|------|----------|-----|
| Trevin's v1.09 docs | Documentation | v1.09 | https://user.xmission.com/~trevin/DiabloIIv1.09_File_Format.shtml |
| krisives/d2s-format | Documentation | v1.10+ | https://github.com/krisives/d2s-format |
| nokka/d2s | Source code (Go) | v1.10+ (partial D2R) | https://github.com/nokka/d2s |
| d07riv (Phrozen Keep) | Forum post | D2R v1.0 | https://d2mods.info/forum/viewtopic.php?t=67135 |
| d07riv converter | Source code | D2R | https://github.com/d07RiV/d07riv.github.io |
| D2SLib (dschu012) | Source code (C#) | D2R | https://github.com/dschu012/D2SLib |
| D2CE (WalterCouto) | Source code (C++) | All versions incl. v98 | https://github.com/WalterCouto/D2CE |
| d2itemreader (squeek502) | Source code (C) | v1.10+ | https://github.com/squeek502/d2itemreader |
| GoMule-Reimagined | Source code (Java) | D2R Reimagined (outdated) | https://github.com/D2R-Reimagined/GoMule-Reimagined |
| D2R Data Guide (locbones) | Documentation | D2R | https://locbones.github.io/D2R_DataGuide/ |
| D2R Reimagined Mod | Data files | D2R + Mod | https://github.com/D2R-Reimagined/d2r-reimagined-mod |
| pairofdocs/atma-stash-d2r | Source code | D2R | https://github.com/pairofdocs/atma-stash-d2r |

---

## Appendix A: Location and Equipped Slot Reference

### Location ID (3 bits)

| Value | Description |
|-------|-------------|
| 0 | Stored (check panel ID) |
| 1 | Equipped |
| 2 | Belt |
| 4 | Cursor (being moved) |
| 6 | Socketed in another item |

### Panel / Storage ID (3 bits)

| Value | Description |
|-------|-------------|
| 1 | Inventory |
| 4 | Horadric Cube |
| 5 | Stash |

### Equipped Slot (4 bits)

| Value | Slot |
|-------|------|
| 1 | Head (Helmet) |
| 2 | Neck (Amulet) |
| 3 | Torso (Armor) |
| 4 | Right Hand (Weapon) |
| 5 | Left Hand (Shield/Weapon) |
| 6 | Right Ring |
| 7 | Left Ring |
| 8 | Waist (Belt) |
| 9 | Feet (Boots) |
| 10 | Hands (Gloves) |
| 11 | Alt Right Hand |
| 12 | Alt Left Hand |

---

## Appendix B: Item Quality Reference

| ID | Quality | Color |
|----|---------|-------|
| 1 | Low Quality | White |
| 2 | Normal | White |
| 3 | Superior | White (with "Superior" prefix) |
| 4 | Magic | Blue |
| 5 | Set | Green |
| 6 | Rare | Yellow |
| 7 | Unique | Gold/Brown |
| 8 | Crafted | Orange |

---

*End of Specification*
