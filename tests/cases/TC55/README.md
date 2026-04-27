# TC55 - Full Endgame Sorceress (Level 100, 87 Items)

## Summary

A fully geared Level 100 Sorceress ("FrozenOrbHydra") with 87 items covering nearly
every item feature: complete Tal Rasha's set (6 pieces, some corrupted/enchanted with
tier upgrades), two Spirit Monarch runeword shields, corrupted unique rings, enchanted
rare boots and unique gloves, 11 unique charms, unique jewels (Facets), worldstone
shards, a gem bag, and belt potions. This is the second-largest stress test after TC49.

Key verification targets:
- **0 garbage items** from 87 total (52 stored, 12 equipped, 5 belt, 18 socketed)
- **Unique name resolution** for has_gfx=1 items via binary_to_star_id carry-chain
- **Tal Rasha's set** with full set bonus activation (6 pieces equipped)
- **Corruption** on 6 items (stat 361/362)
- **Enchantments** on 3 items (stat 392/393/394)
- **Runeword shields** (2x Spirit Monarch, 28-bit sock_unk)
- **Tier-upgraded set items** (same set piece at [X] and [E] quality with different item codes)

## Character Overview

| Field     | Value          |
|-----------|----------------|
| Name      | FrozenOrbHydra |
| Class     | Sorceress      |
| Level     | 100            |

## Complete Item Table

**Legend:** sb = set bonus props, rw = runeword display props.
**Flags:** RW = Runeword, ETH = Ethereal, CORR = Corrupted, ENC = Enchanted, GFX = Custom Graphics.

| # | Location | Code | Quality | Sock | Props | Name | Flags |
|---|----------|------|---------|------|-------|------|-------|
| 1 | Stash (4,5) | `cm3` | Crafted | - | 8 | (Crafted Grand Charm) | GFX |
| 2 | Stash (9,6) | `cm1` | Unique | - | 14 | Black Soulstone | GFX |
| 3 | Stash (13,0) | `xtg` | Unique | - | 8 | Magefist | |
| 4 | Stash (0,11) | `xhm` | Set | 3 | 9 | Guillaume's Face [X] | ETH,CORR |
| 5-7 | Socketed | `r30` | Simple | - | - | Ber Rune (*3) | |
| 8 | Stash (0,9) | `xhm` | Set | - | 5 | Guillaume's Face [X] | |
| 9 | Stash (5,0) | `cm3` | Unique | - | 4 | Triskelion | GFX |
| 10 | Stash (8,10) | `xit` | Normal | - | 1 | Dragon Shield | |
| 11 | Stash (14,11) | `xtb` | Unique | - | 10 | Halbu's Gift | |
| 12 | Stash (6,10) | `uit` | Magic | - | 2 | (Magic Monarch) | |
| 13 | Stash (10,10) | `kit` | Magic | - | 3 | (Magic Kite Shield) | |
| 14 | Stash (4,0) | `cm3` | Crafted | - | 8 | (Crafted Grand Charm) | GFX |
| 15 | Stash (12,11) | `xtb` | Rare | - | 4 | (Rare War Hammer) | |
| 16 | Stash (12,9) | `xtb` | Unique | - | 10 | Halbu's Gift | |
| 17 | Stash (0,7) | `xhm` | Set | - | 5 | Guillaume's Face [X] | |
| 18 | Stash (9,0) | `uth` | Set | - | 11+2sb | Tal Rasha's Guardianship [E] | CORR |
| 19 | Stash (7,0) | `xsk` | Set | - | 10+2sb | Tal Rasha's Horadric Crest [X] | |
| 20 | Stash (7,2) | `zmb` | Set | - | 6+2sb | Tal Rasha's Fine-Spun Cloth [X] | |
| 21 | Stash (11,0) | `oba` | Set | - | 8+6sb | Tal Rasha's Lidless Eye [X] | |
| 22 | Stash (14,9) | `ci3` | Normal | 3 | 0 | Diadem [E] (3 empty sockets) | |
| 23 | Stash (6,0) | `amu` | Set | - | 7+2sb | Tal Rasha's Adjudication | GFX |
| 24 | Stash (15,0) | `ob5` | Unique | - | 11 | Eternity Cable | |
| 25 | Stash (15,4) | `jew` | Unique | - | 6 | Winter Facet | GFX |
| 26 | Stash (14,6) | `uit` | Magic | - | 2 | (Magic Monarch) | |
| 27-29 | Stash (3,0-2) | `xa1` | Normal | - | 0 | Worldstone Shard (*3) | |
| 30 | Stash (9,7) | `bag` | Normal | - | 1 | Gem Bag (28 gems) | |
| 31 | Stash (15,3) | `jew` | Unique | - | 5 | Spring Facet | GFX |
| 32 | Stash (4,3) | `cm1` | Unique | - | 8 | Remembrance of Glory | GFX |
| 33 | Stash (4,4) | `cm1` | Unique | - | 5 | Peacemaker | GFX |
| 34 | Stash (7,0) | `cm3` | Unique | - | 4 | Gheed's Fortune | GFX |
| 35 | Stash (8,0) | `cm3` | Unique | - | 5 | Web of Wyrd | GFX |
| 36 | Stash (6,0) | `cm3` | Unique | - | 10 | Queen's Call | GFX |
| 37 | Stash (5,3) | `cm3` | Crafted | - | 12 | (Crafted Grand Charm) | GFX |
| 38 | Stash (6,3) | `cm3` | Crafted | - | 4 | (Crafted Grand Charm) | GFX |
| 39 | Stash (7,5) | `cm3` | Unique | - | 12 | Obsidian Beacon | GFX |
| 40 | Stash (3,3) | `xa1` | Normal | - | 0 | Worldstone Shard | |
| 41 | Stash (7,3) | `cm2` | Unique | - | 4 | Life & Death | GFX |
| 42 | Stash (8,6) | `cm2` | Unique | - | 5 | Ogre King's Bowl | GFX |
| 43 | Equipped (1,0) | `usk` | Set | 4 | 10+12sb | Tal Rasha's Horadric Crest [E] | |
| 44-47 | Socketed | `jew` | Unique | - | - | Facets (*4) | |
| 48 | Equipped (2,0) | `amu` | Set | - | 7+14sb | Tal Rasha's Adjudication | GFX |
| 49 | Equipped (3,0) | `uth` | Set | 4 | 7+8sb | Tal Rasha's Guardianship [E] | |
| 50 | Equipped (6,0) | `rin` | Unique | - | 15 | Plantar Enlightenment | CORR,ENC,GFX |
| 51 | Equipped (7,0) | `rin` | Unique | - | 16 | Plantar Enlightenment | CORR,ENC,GFX |
| 52 | Equipped (8,0) | `umc` | Set | - | 6+6sb | Tal Rasha's Fine-Spun Cloth [E] | |
| 53 | Equipped (9,0) | `uhb` | Rare | - | 17 | (Rare Boots) | CORR,ENC=3 |
| 54 | Equipped (10,0) | `umg` | Unique | - | 16 | Lachdanan's Bracers | CORR,ENC=3 |
| 55 | Stash (5,6) | `cm2` | Unique | - | 8 | Valknut | GFX |
| 56 | Stash (6,6) | `cm2` | Unique | - | 11 | Throne of Power | GFX |
| 57 | Stash (3,4) | `xa1` | Normal | - | 0 | Worldstone Shard | |
| 58 | Stash (9,2) | `ibk` | Normal | - | 0 | Tome of Identify | |
| 59 | Stash (8,3) | `cm1` | Unique | - | 7 | Argo's Anchor | GFX |
| 60 | Stash (14,4) | `jew` | Unique | - | 6 | Winter Facet | GFX |
| 61-63 | Stash | `jew` | Magic | - | 1-4 | (Magic Jewels *3) | GFX |
| 64-69 | Belt | `rvl` | Simple | - | 0 | Full Rejuvenation Potion (*5) | |
| 66 | Stash (2,7) | `jew` | Magic | - | 3 | (Magic Jewel) | GFX |
| 70 | Stash (3,6) | `jew` | Magic | - | 1 | (Magic Jewel) | GFX |
| 71 | Stash (9,0) | `tbk` | Normal | - | 0 | Tome of Town Portal | |
| 72 | Stash (8,4) | `box` | Normal | - | 0 | Horadric Cube | |
| 73 | Equipped (12,0) | `uit` | Normal | 4 | 7rw | Spirit Monarch #1 | RW |
| 74-77 | Socketed | `r07,r10,r09,r11` | Simple | - | - | Tal+Thul+Ort+Amn | |
| 78 | Equipped (11,0) | `gwn` | Magic | - | 3 | (Magic Wand - Life Tap charges) | |
| 79 | Equipped (4,0) | `obf` | Set | 3 | 8+13sb | Tal Rasha's Lidless Eye [E] | |
| 80-82 | Socketed | `jew` | Unique | - | - | Winter Facets (*3) | |
| 83 | Equipped (5,0) | `uit` | Normal | 4 | 12rw | Spirit Monarch #2 (corrupted+enchanted) | RW |
| 84-87 | Socketed | `r07,r10,r09,r11` | Simple | - | - | Tal+Thul+Ort+Amn | |

## Notable Items

### Tal Rasha's Set (6 pieces equipped, full set bonus)

Some pieces exist in both [X] (Exceptional) and [E] (Elite) tiers due to tier upgrades.
The equipped versions are the upgraded [E] tier with different item codes from the stash copies.

| Piece | Stash Code | Equipped Code | Tier Change |
|-------|-----------|---------------|-------------|
| Horadric Crest (Helm) | `xhm` [X] | `usk` [E] | Death Mask -> Demonhead |
| Guardianship (Armor) | `uth` [E] | `uth` [E] | (same) |
| Fine-Spun Cloth (Belt) | `zmb` [X] | `umc` [E] | Mesh Belt -> Mithril Coil |
| Lidless Eye (Orb) | `oba` [X] | `obf` [E] | Swirling Crystal -> Dimensional Shard |
| Adjudication (Amulet) | `amu` | `amu` | (same - amulets have no tiers) |

### Spirit Monarchs (2x Runeword)

- **#73** (main hand): FCR=32, FHR=20, Mana=64, +2 Skills, Absorb=8
- **#83** (switch): FCR=35, FHR=20, Mana=104, +2 Skills, Absorb=6, Block=25 - corrupted+enchanted (in RW display props)

### Corrupted Items

| # | Item | Corruption Roll |
|---|------|----------------|
| 4 | Guillaume's Face (ETH, 3* Ber) | 152 |
| 18 | Tal Rasha's Guardianship (Stash) | 148 |
| 50 | Plantar Enlightenment (Ring #1) | 161 |
| 51 | Plantar Enlightenment (Ring #2) | 170 |
| 53 | Rare Boots | 187 |
| 54 | Lachdanan's Bracers | 141 |

### Enchanted Items

| # | Item | Enchant Stat | Count |
|---|------|-------------|-------|
| 53 | Rare Boots | upgrade_medium (393) | 3 |
| 54 | Lachdanan's Bracers | upgrade_medium (393) | 3 |

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC55/FrozenOrbHydra.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC55/FrozenOrbHydra.d2s
```
