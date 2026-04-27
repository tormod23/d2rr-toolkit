# D2RR Toolkit - Binary Verification Log

The per-field audit trail for every `.d2s` / `.d2i` binary claim the
parser relies on. Each row is either empirically verified against a
real save (`[BV]`) or marked as spec-only (`[SPEC]`) pending
verification. The `[BV TC##]` variant names the specific fixture
under `tests/cases/TC##/` that pinned the claim; check that
fixture's own `README.md` for the scenario details.

**Tags:**

| Tag | Meaning |
|---|---|
| `[BV]` / `[BINARY_VERIFIED]` | Confirmed against real save files. Safe for production parser / writer code. |
| `[BV TC##]` | Confirmed against the specific test case `TC##`. |
| `[TC##]` | Exercised by the named test case (tighter than `[SPEC]`, less formal than `[BV]`). |
| `[SPEC]` / `[SPEC_ONLY]` | From the public D2S format spec, not yet binary-verified. Treat with caution. |
| `[UNKNOWN]` | Not in spec, not yet researched. Region preserved verbatim, never guessed. |

See [`CONTRIBUTING.md`](CONTRIBUTING.md#verification-tags) for the full
contract (what each tag means, how to promote `[SPEC]` -> `[BV]`,
workflow for adding a new field).

---

## 1. File Structure

### 1.1 Signature & Version

| Field | Offset | Width | Value | Status |
|---|---|---|---|---|
| Signature | 0x00 | uint32 | `0xAA55AA55` | [BV] |
| Version | 0x04 | uint32 | **105** (0x69) | [BV] |

### 1.2 Header Layout (v105)

Header size: **833 bytes** (+68 vs v97 spec of 765).

| Field | Offset | Width | Status |
|---|---|---|---|
| Character class | 0x18 | 1 byte | [BV] |
| Character level | 0x1B | 1 byte | [BV] |
| Character name | 0x12B | null-terminated ASCII | [BV] |

### 1.3 Section Markers (v105 offsets)

| Marker | Offset | Purpose | Status |
|---|---|---|---|
| `"gf"` | byte 833 | Stats section start | [BV] |
| `"if"` | after stats | Skills section (2 + 30 bytes) | [BV] |
| `"JM"` + uint16 | after skills | Item list (count = all player items) | [BV] |
| `"JM"` + uint16 | after items | Corpse item list (normally count=0) | [BV] |
| `"jf"` | after corpse | Mercenary section | [BV TC49] |
| `"JM"` + uint16 | after jf | Mercenary item list | [BV TC49] |

### 1.4 Character Stats (bit-level)

Plain LSB-first bit reading, no bit-reversal. Zero-value stats omitted.
Terminated by 9-bit `0x1FF`.

| Stat ID | Name | CSvBits | Status |
|---|---|---|---|
| 0-3 | Str / Energy / Dex / Vit | 10 | [BV] |
| 4 | Stat points | 10 | [BV] |
| 5 | Skill points | 8 | [BV] |
| 6-11 | HP / Mana / Stamina (cur+max) | 21 | [BV] Fixed-point /256 |
| 12 | Level | 7 | [BV] |
| 13 | Experience | 32 | [BV] |
| 14-15 | Gold (inventory / stash) | 25 | [BV] |

All bit-widths come from `ItemStatCost.txt` CSvBits column at runtime.

### 1.5 Class IDs

| ID | Class | Status |
|---|---|---|
| 0 | Amazon | [BV TC07] |
| 1 | Sorceress | [BV] |
| 2 | Necromancer | [BV TC17] |
| 3 | Paladin | [BV TC08-TC10] |
| 4 | Barbarian | [BV TC01, TC02] |
| 5 | Druid | [BV TC14] |
| 6 | Assassin | [BV TC15, TC16, TC22] |
| 7 | Warlock | [BV TC03, TC11, TC49] |

---

## 2. Item Binary Format

### 2.1 Item Header (53 flag bits)

```text
Bit  W  Field                  Status
---  -  ---------------------  ------
  4  1  identified             [BV]
 11  1  socketed               [BV]
 17  1  starter_item           [BV]
 21  1  simple_item            [BV]
 22  1  ethereal               [BV TC37]
 24  1  personalized           [BV]
 26  1  runeword               [BV TC45]
35-37 3  location_id            [BV] 0=Stored, 1=Equipped, 2=Belt, 6=Socketed
38-41 4  equipped_slot          [BV]
42-45 4  position_x             [BV]
46-49 4  position_y             [BV]
50-52 3  panel_id               [BV]
  53+ var Huffman item code     [BV] d07riv table at bit 53
```

### 2.2 Extended Item Header

After the Huffman code (for non-simple items):

```text
Field                  Width   Status
---------------------  ------  ------
socket_filled_count    3 bits  [BV]
fingerprint            32 bits [BV]
item_level             7 bits  [BV]
quality                4 bits  [BV]
has_gfx                1 bit   [BV]
  gfx_index            3 bits  [BV] (only if has_gfx=1)
  gfx_extra            1 bit   [BV TC41-TC44] (only if has_gfx=1)
has_class              1 bit   [BV]
  automod              11 bits [BV TC09/TC14/TC40] (conditional, see 2.3)
quality_specific_data  varies  [BV TC02/TC39/TC40]
runeword_id            12 bits [BV TC45/TC48] (only if runeword flag)
rw_unknown             4 bits  [BV]
personalized_name      var     [SPEC] (only if personalized flag)
timestamp              1 bit   [BV TC40-TC43]
```

### 2.3 Automod Rules

| Item Type | bf1 | When Read | Status |
|---|---|---|---|
| Armor / weapons with auto_prefix | True | Only when has_class=1 | [BV TC09, TC14] |
| Charms / tools / orbs with auto_prefix | False | ALWAYS (except Unique q=7) | [BV TC17, TC19, TC43] |
| Jewels / rings / amulets (no auto_prefix) | - | NEVER (has_class flows into carry-chain) | [BV TC24, TC42] |

### 2.4 gfx_extra Carry-Chain (has_gfx=1 only)

The 1-bit gfx_extra field shifts all subsequent QSD values by 1 bit.

| Quality | Formula | Status |
|---|---|---|
| Unique (q=7) | `*ID = uid*2 + has_class - 2` | [BV TC39, TC42] |
| Set (q=5) | `*ID = set_id*2 + has_class` | [BV] |
| Magic (q=4) | `prefix = (has_class \| (raw<<1)) - 1` | [BV TC41] |
| Rare (q=6) | `name1 = (has_class \| (raw<<1)) - 156` | [BV TC40] |

### 2.5 Quality-Specific Data

| Quality | Name | Extra Bits | Status |
|---|---|---|---|
| 1 | Low | 3 bits | [SPEC] |
| 2 | Normal | 0 bits | [BV TC08-TC10] |
| 3 | Superior | 3 bits | [BV TC02, TC11] |
| 4 | Magic | 11+11 (prefix+suffix) | [BV TC02, TC41, TC43] |
| 5 | Set | 12 bits (set_item_id) | [BV TC02, TC36, TC47] |
| 6 | Rare | 8+8 + 6*(1+opt 11) + opt 7th(1+10) | [BV TC02, TC24, TC40] |
| 7 | Unique | 12 bits (unique_id) | [BV TC02, TC39, TC42] |
| 8 | Crafted | Same as Rare | [BV TC26] |

### 2.6 Armor + Weapon Type-Specific Layout

**Armor** (all 218 Reimagined rows have `durability > 0`):

```text
defense(11) + max_dur(8) + cur_dur(8) + unk_post(2)   = 29 bits
```

**Weapons** - the durability block is **variable-width**, gated by
`max_dur == 0` (the sentinel for "no durability at all"):

```text
max_dur > 0   (normal weapons, all bows, crossbows, etc.):
    max_dur(8) + cur_dur(8) + unk_post(2)             = 18 bits

max_dur == 0  (Phase Blade `7cr` - the ONLY weapon with
               `durability=0` in weapons.txt):
    max_dur(8)               + unk_post(1)            =  9 bits
```

`unk_post` flips from 2 bits to 1 bit when `cur_dur` is omitted.
`nodurability=1` in `weapons.txt` is NOT a reliable predicate on its
own - Reimagined sets it on every bow / crossbow that still carries
`durability=250`. The authoritative static predicate is
`weapons.txt.durability > 0`; the authoritative runtime predicate is
the read `max_dur` value. [BV TC56 Lightsabre - canonical regression
fixture.]

Then if socketed (armor + weapons):

| Type | Layout | Status |
|---|---|---|
| Non-RW, non-Unique shield | shield_unknown(2) + sock(4) | [BV TC32] |
| Unique shield (non-RW) | sock(4) only, NO shield_unknown | [BV TC56] |
| RW shield | sock(4) + rw_data(24) = 28 bits | [BV TC45] |
| Superior non-RW | sock_unknown(20) = count(4) + quality(16) | [BV TC11] |
| All others | sock_count(4) | [BV TC24, TC37, TC46] |

If quality=5: `set_bonus_mask(5)` follows. [BV TC02, TC36, TC37, TC47]

### 2.7 ISC Property Encoding

9-bit stat IDs until 0x1FF terminator.

| Encode | Layout | Status |
|---|---|---|
| 0 | `stat_id(9) + [param(save_param_bits)] + value(save_bits)` | [BV] |
| 1 | Same as 0, but paired stat follows (no separate ID) | [BV TC33] |
| 2 | `stat_id(9) + param(save_param_bits) -> level(6)+skill(10), then value` | [BV TC35] |
| 3 | `stat_id(9) + param -> level(6)+skill(10), then max_charges(8)+charges(8)` | [BV TC35] |
| 4 | `stat_id(9) + extra(save_bits or 14)` | [BV TC01] |

Hardcoded pairs (game engine, NOT in ISC):
17->18, 48->49, 50->51, 52->53, 54->55->56, 57->58->59.

### 2.8 Inter-Item Padding

Some items have 8-56 bits of padding after the 0x1FF terminator.

| Pattern | Width | Items Affected | Status |
|---|---|---|---|
| Standard misc padding | 8 bits | Charms, tools, orbs (bf1=False) | [BV TC16, TC19] |
| Unique Jewel padding | 56 bits (7 bytes) | Unique Jewels with has_gfx=1 | [BV TC44, TC48, TC49] |
| Weapon gaps | 48 bits | Between weapon types | [BV TC33] |

Padding is detected by probing for valid Huffman codes at 8-bit
intervals (0..56).

### 2.9 Runeword Second Property List

Runeword items carry a second ISC property list after the byte-aligned
base properties. Structure:
`[internal state] + [display properties] + 0x1FF`.

Display-property decoder uses a scan-based approach with 3
false-positive filters:

1. Bytime values > 10,000 = internal state [BV TC24]
2. Non-ascending stat IDs = drift [BV TC24]
3. Damage pair min > max = impossible [BV TC24]

Coverage: [BV TC38, TC39, TC45, TC48].

---

## 3. Spec Corrections (v97 -> v105)

| Field | v97 Spec | v105 Actual | Status |
|---|---|---|---|
| File version | 98 | **105** | [BV] |
| Header size | 765 bytes | **833 bytes** (+68) | [BV] |
| Character name offset | 0x14 | **0x12B** | [BV] |
| Character class offset | 0x28 | **0x18** | [BV] |
| Character level offset | 0x2B | **0x1B** | [BV] |
| Huffman code offset | bit 60 | **bit 53** | [BV] |
| `unique_item_id` width | 32 bits | **35 bits** | [BV] |
| Durability widths | 9+9 bits | **8+8 bits** | [BV] |
| Stats bit-reversal | Required | **Not required** | [BV] |
| Root JM scope | Inventory only | **All items** | [BV] |

---

## 4. GUI Socket Overlay Layout

Sockets are positioned via `_SOCKET_ROW_COUNTS` in
`src/d2rr_toolkit/display/item_display.py`, keyed by
`(inv_width, inv_height, num_sockets)` and returning a list of row
counts (top -> bottom). In-game D2RR verified layouts:

| Item Dims | Sockets | Row Counts | Notes |
|---|---|---|---|
| 2x2 | 2 | `[1, 1]` | Vertical stack, no horizontal offset |
| 2x2 | 3 | `[1, 2]` | Single top (centred), pair bottom |
| 2x2 | 4 | `[2, 2]` | Two pairs |
| 2x3 | 2 | `[1, 1]` | Centred vertically (y_offset=0.5) |
| 2x3 | 3 | `[1, 1, 1]` | Full-height single column |
| 2x3 | 4 | `[2, 2]` | Two pairs, centred |
| 2x3 | 5 | `[2, 1, 2]` | Pair / centre / pair |
| 2x3 | 6 | `[2, 2, 2]` | Three pairs |
| 2x4 | 4 | `[1, 1, 1, 1]` | Four single rows |
| 2x4 | 5 | `[2, 1, 2]` | Pair / centre / pair, vertically centred |
| 2x4 | 6 | `[2, 2, 2]` | Three pairs |

**Centring math:**
`y_offset = (inv_h - rows) / 2.0` centres the grid vertically;
`x_offset = (inv_w - count) / 2.0` centres each row horizontally.
Positions are in cell-unit coordinates (0.5 = half-cell offset).

**Edge cases:**
`num_sockets <= 0` -> empty list. Undefined `(w, h, n)` -> empty list
(no crash). Socket positions always fall within
`[0, w-0.5] * [0, h-0.5]`.

Coverage: `tests/test_socket_layout.py` - 107 checks pass.

---

## 5. Section 5 Writer Binary Layout

**Simple items** (`flags.simple=1` - runes, gems, orbs, simple
stackables):

- 9-bit quantity field at item-relative bit
  `53 + huffman_bits + 1` (after flags + Huffman + 1 socket bit).
- Raw encoding: `(display_value << 1) | lsb_flag`, where `lsb_flag`
  is preserved verbatim by the patcher.
- Display range: 1..99 (game cap).
- Parser instrumentation: `ParsedItem.quantity_bit_offset` set in
  `_parse_single_item` simple path.

**Extended AdvancedStashStackable items** (`flags.simple=0`, `ASS=1`,
`stackable=0` - keys, relics, worldstone shards, pliers, quest organs,
gem cluster):

- 7-bit quantity field at the reader position directly after the
  `0x1FF` ISC terminator + 1 extra bit.
- Raw encoding: direct display value (no LSB flag).
- Display range: 1..99.
- Parser instrumentation: `_misc_qty_bit_offset` captured in
  `_parse_type_specific_data` ASS branch, passed to `ParsedItem`
  constructor.

### Game behaviour rules (in-game verified)

| Rule | Writer response |
|---|---|
| One stack per item_code in Section 5 (duplicates silently dropped by the game) | `DuplicateSection5ItemError` raised by `D2IWriter.build()`. |
| Quantity=0 persists as an invisible zombie, is NOT a remove | `ValueError` in `patch_item_quantity` for quantity < 1; use tab-list removal instead. |
| Max quantity = 99 | `ValueError` for quantity > 99. |
| Grid-tab items transferable cross-file (panel_id=5) | Existing `patch_item_position` helper is sufficient. |

Coverage: [BV TC61].
