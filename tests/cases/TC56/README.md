# TC56 - Full Endgame Sorceress (Level 100, 136 Items, Weapon Switch + Runeword)

## Summary

A fully geared Level 100 Sorceress ("VikingBarbie") with 136 player items, 9 merc
items, and a Spirit Runeword on the weapon switch. This is the most complex test
character, featuring all 12 equipped slots (including weapon switch), 53 unique items,
13 corrupted items, 9 enchanted items, 67 items with custom graphics (has_gfx=1),
6 crafted items, and a 3-piece set (ring+ring+amulet) with corruption and enchantments.

This TC exposed four critical parser bugs (first three fixed 2026-04-06,
fourth fixed 2026-04-17):
1. **Superior Runeword single-list format** - Superior quality runewords have no
   separate base-props 0x1FF, all stats in one list (stat 386 detection)
2. **Superior shield sock_unk width** - Superior shields have no shield_unk(2),
   only unk(2) + sock_count(4) = 6 bits after durability
3. **Extra items Huffman pre-validation** - padding bytes before corpse JM were
   misread as items; Huffman code validity check stops the loop correctly
4. **Phase Blade variable-width durability block** - weapons with
   ``durability=0`` in weapons.txt (only Phase Blade in Reimagined 3.0.7)
   use a 9-bit durability block ``max_dur(8) + unk(1)`` instead of the
   18-bit ``max_dur(8) + cur_dur(8) + unk(2)`` shape used by every
   other weapon.  VikingBarbie's Lightsabre (unique Phase Blade,
   ``*ID=259``) is the canonical regression fixture; pre-fix output
   rendered the item as garbage (fire_dam=2.9M, Adds 19-0 Weapon
   Damage, +3.6M% Enhanced Defense).

Key verification targets:
- **0 trailing bytes** (was 642 before fixes)
- **136 player items** (was 115 before fixes)
- **All 12 equipped slots** populated (was 8 before fixes)
- **1 runeword** - Spirit Monarch on weapon switch (Superior quality, single-list format)
- **53 unique names** verified correct
- **67 has_gfx=1 items** - massive carry-chain stress test (49% of all items)
- **Knight's Dawn**: Unique Aegis, 4 sockets (exposed shield_unk bug for q=7)
- **13 corrupted + 9 enchanted** items
- **Gem Bag with 1704 gems** (confirmed in-game)
- **16 belt items** (maximum belt grid)
- **9 merc items** (3 equipped + 6 socketed; 7 more expected, merc parser limitation)

## Character Overview

| Field     | Value        |
|-----------|--------------|
| Name      | VikingBarbie |
| Class     | Sorceress    |
| Level     | 100          |

## Inventory Summary

| Category | Count |
|----------|-------|
| Stored (Stash + Cube + Misc) | 85 |
| Equipped (Main + Switch) | 12 |
| Belt | 16 |
| Socketed (children) | 23 |
| **Total** | **136** |

## Equipped Items

### Main Equipment

| Slot | Name | Quality | Flags |
|------|------|---------|-------|
| Armor | Shadowtrick (Shadow Plate) | Unique | CORR, ENC=5, 4 sockets (4x Heaven Facet) |
| Helm | Ragnarok (Corona) | Unique | CORR, ENC=3, 4 sockets (4x Heaven Facet) |
| Belt | Lachdanan's Wrap (Troll Belt) | Unique | CORR, ENC=3 |
| Boots | (Crafted) Mirrored Boots | Crafted | CORR, ENC=3, 21 properties |
| Gloves | Rapturous Blessings (Ogre Gauntlets) | Unique | CORR, ENC=3 |
| Ring 1 | Demonic Chuckle | Set | CORR, ENC=2 |
| Ring 2 | Evil Humor | Set | CORR, ENC=2 |
| Amulet | Temptation's Death | Set | CORR, ENC=2 |

### Main Weapon + Shield

| Slot | Name | Quality | Stats |
|------|------|---------|-------|
| Right Hand | Frost Wyrm (Berserker Axe) | Unique | 6 sockets (6x Jewel), 23 properties |
| Left Hand | Knight's Dawn (Aegis) | Unique | 4 sockets (4x Jewel), 20 properties |

Frost Wyrm in-game stats (user-verified):
- One-Hand Damage: 96 to 286
- +304% Enhanced Weapon Damage, +300 Attack Rating
- Fire/Lightning/Cold Weapon Damage, Elemental Pierce/Mastery
- Multiple skill-on-event procs (Meteor, Comet, Winter's Pulse, etc.)
- Enchantments: 1/5, Corrupted

Knight's Dawn in-game stats (user-verified):
- Defense: 383, Chance to Block: 59%
- +146% Enhanced Defense, +15% All Resistances, +5% All Max Resistances
- +1 All Skills, +1 Holy Shield (oskill), +3 Vengeance (oskill)
- Enchantments: 5/5, Corrupted

### Weapon Switch

| Slot | Name | Quality | Stats |
|------|------|---------|-------|
| Right Hand | Warrior Untamed (War Sword) | Unique | 1 socket (Hel Rune), 11 properties |
| Left Hand | Spirit (Monarch) | Superior RW | 4 sockets (Tal+Thul+Ort+Amn), 7 RW properties |

Spirit in-game stats (user-verified):
- Defense: 140, Durability: 95/95
- +2 All Skills, +30% FCR, +22% FHR, +250 Defense vs Missile
- +22 Vitality, +54 Mana, +8 Magic Absorb
- +35% Cold/Lightning/Poison Resist (from runes)
- Attacker Takes Damage of 14, +11% Max Durability (Superior)

## Parser Bug Discoveries

### 1. Superior Runeword Single-List Format (fix/rw-superior-no-base-terminator)

Superior (q=3) runeword items store ALL properties in ONE 0x1FF-terminated list.
Normal/Crafted runewords have two lists: [base props][0x1FF][RW ISC][0x1FF].
Superior runewords: [RW ISC including stat 386][0x1FF] (no base-props terminator).
The Superior modifier (+11% Max Dur) is implicit from superiority_type, not a stat.

Detection: stat 386 (stacked_gem) found in base magical_properties.

### 2. Superior Shield Socket Width (fix/rw-superior-no-base-terminator)

Superior non-RW shields have only unk(2) + sock_count(4) = 6 bits after durability.
Previous code read shield_unk(2) + sock_unk(20) = 24 bits, causing ED% and MaxDur%
to be consumed as socket data. Verified with TestSorc.d2s (3 Superior Monarchs).

### 3. Huffman Pre-Validation (fix/rw-superior-no-base-terminator)

48 bits of inter-item padding before the corpse JM decoded as Huffman code 'bt'
(valid Huffman, invalid item). The parser tried to parse it as an item, consuming
data past the corpse JM. Fix: probe Huffman code against item DB before parsing.

### Previous: Unique Shield socket_unk (fix from earlier session)

Unique (q=7) shields do not have shield_unk(2) bits. Without this fix, Knight's Dawn
socket count reads as 0 instead of 4.

## TestSorc.d2s (Additional Test File)

Three Superior Monarchs with varying ED% and MaxDur% for socket width verification:

| Position | Enhanced Defense | Max Durability | Sockets |
|----------|-----------------|----------------|---------|
| (0,0) | +2% | +3% | 4 |
| (2,0) | +15% | +12% | 4 |
| (4,0) | +12% | +7% | 4 |

## Merc Items (Partial Parse)

9 of expected 16 items parsed (merc JM count = 9):
- Mirrored Boots (equipped, no sockets)
- Corona (equipped, 4 sockets: Ber + Lem + Um + Ist)
- Great Hauberk (equipped, 4 sockets: 2x Ber + more expected)

Missing: weapon (5 sockets) and remaining socket children. Merc parser needs
extra-items logic similar to the player item parser fix.

## Verified In-Game

| Item | Verified | Status |
|------|----------|--------|
| Gem Bag = 1704 gems | Yes | OK |
| Knight's Dawn = 4 sockets | Yes (exposed q=7 bug -> fixed) | OK |
| Crafted Boots stats | Yes | OK |
| Spirit Monarch stats | Yes (exposed Superior RW bug -> fixed) | OK |
| Frost Wyrm stats | Yes | OK |
| Knight's Dawn stats | Yes | OK |
| Warrior Untamed stats | Yes | OK |
| 3x Superior Monarch ED%+MaxDur% | Yes (exposed shield sock_unk bug -> fixed) | OK |
| Lightsabre (unique Phase Blade) stats | Yes (exposed Phase Blade durability=0 bug -> fixed) | OK |

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC56/VikingBarbie.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC56/VikingBarbie.d2s
```
