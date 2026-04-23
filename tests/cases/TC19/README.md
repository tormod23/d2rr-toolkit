# TC19 - Graphic Variants for Amulets, Small/Large/Grand Charms

## Summary

Character with all standard graphic variants (3 each) plus one unique (custom graphic)
for amulets, small charms, large charms, and grand charms. This tests the `gfx_index`
field mapping to visual appearance variants.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Map gfx_index values to known visual variants for misc items.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0           C1           C2           C3
R0 [Amu-Sun]    [Amu-Cross]  [Amu-Star]   [Amu-Unique]
R1 [SC-Ftball]  [SC-BClaw]   [SC-Coin]    [SC-Unique]
R2 [LC-Paper]   [LC-Horn]    [LC-Obelisk] .
R3 [LC-Paper]   [LC-Horn]    [LC-Obelisk] [LC-Unique]
R4 [GC-Monst]   [GC-DNA]     [GC-Eye]     [LC-Unique]
R5 [GC-Monst]   [GC-DNA]     [GC-Eye]     .
R6 [GC-Monst]   [GC-DNA]     [GC-Eye]     [GC-Unique]
R7 .            .            .            [GC-Unique]
                                          [GC-Unique]
```

Items: 4 amulets + 4 small charms + 4 large charms + 4 grand charms = 16 total

## Item Details

### Amulets (Size 1x1)

| # | Pos   | Visual Variant | Quality | Name | iLVL | Properties |
|---|-------|---------------|---------|------|------|------------|
| 1 | (0,0) | Sun           | Magic   | Gnostic Amulet of Chilling Coalescence | 95 | +2 to Blades of Ice (Assassin only), 17% Cold Damage Absorbed |
| 2 | (1,0) | Cross         | Magic   | Fanatic Amulet | 99 | +1 to Masteries & Throwing Skills (Barbarian only) |
| 3 | (2,0) | Star          | Magic   | Amulet of the Apprentice | 96 | 10% Faster Cast Rate |
| 4 | (3,0) | Custom (Unique) | Unique | Eye of Khan | 99 | +3 Max Weapon Dmg, +9 Str, +6 Dex, +33 Life, +35 Mana |

### Small Charms (Size 1x1)

| # | Pos   | Visual Variant | Quality | Name | iLVL | Properties |
|---|-------|---------------|---------|------|------|------------|
| 5 | (0,1) | Football      | Magic   | Small Charm of Flame | 9 | Adds 1-4 Weapon Fire Damage |
| 6 | (1,1) | Bear Claw     | Magic   | Small Charm of the Weasel | 2 | +10 to Attack Rating |
| 7 | (2,1) | Coin          | Magic   | Small Charm of the Icicle | 98 | Adds 3-8 Weapon Cold Damage |
| 8 | (3,1) | Custom (Unique) | Unique | Argo's Anchor | 99 | 9% Block, +12 Max Dmg, +73 AR, +22% MF |

### Large Charms (Size 1x2)

| # | Pos   | Visual Variant | Quality | Name | iLVL | Properties |
|---|-------|---------------|---------|------|------|------------|
| 9 | (0,2) | Paper         | Magic   | Gaian Large Charm of the Young | 99 | +4% Cold Skill Dmg, +4 Vit, +4 Energy |
| 10| (1,2) | Horn          | Magic   | Lucky Large Charm | 98 | +39% Gold, +16% MF |
| 11| (2,2) | Obelisk       | Magic   | Large Charm of Mastery | 94 | -5% Enemy Lightning Res |
| 12| (3,3) | Custom (Unique) | Unique | Valknut | 99 | +9% Dex, +10% Energy, +8 All Attr, +9% Exp |

### Grand Charms (Size 1x3)

| # | Pos   | Visual Variant | Quality | Name | iLVL | Properties |
|---|-------|---------------|---------|------|------|------------|
| 13| (0,4) | Monster       | Magic   | Fiendish Grand Charm of Pestilence | 99 | +1 Demon Skills (Warlock only), 39-47 Poison Dmg/4s |
| 14| (1,4) | DNA           | Magic   | Grand Charm of Shock | 10 | Adds 3-7 Weapon Lightning Dmg |
| 15| (2,4) | Eye           | Magic   | Grand Charm of Frost | 5 | +6 Weapon Cold Damage |
| 16| (3,4) | Custom (Unique) | Unique | Conclave of Elements | 84 | 63-511 Fire/Lightning/Cold Dmg |

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    # Amulets
    - name: "Gnostic Amulet of Chilling Coalescence"
      pos: [0, 0]
      quality: "magic"
      item_level: 95
      visual_variant: "Sun"
    - name: "Fanatic Amulet"
      pos: [1, 0]
      quality: "magic"
      item_level: 99
      visual_variant: "Cross"
    - name: "Amulet of the Apprentice"
      pos: [2, 0]
      quality: "magic"
      item_level: 96
      visual_variant: "Star"
    - name: "Eye of Khan"
      pos: [3, 0]
      quality: "unique"
      item_level: 99
      visual_variant: "Custom"
    # Small Charms
    - name: "Small Charm of Flame"
      pos: [0, 1]
      quality: "magic"
      item_level: 9
      visual_variant: "Football"
    - name: "Small Charm of the Weasel"
      pos: [1, 1]
      quality: "magic"
      item_level: 2
      visual_variant: "Bear Claw"
    - name: "Small Charm of the Icicle"
      pos: [2, 1]
      quality: "magic"
      item_level: 98
      visual_variant: "Coin"
    - name: "Argo's Anchor"
      pos: [3, 1]
      quality: "unique"
      item_level: 99
      visual_variant: "Custom"
    # Large Charms
    - name: "Gaian Large Charm of the Young"
      pos: [0, 2]
      quality: "magic"
      item_level: 99
      visual_variant: "Paper"
    - name: "Lucky Large Charm"
      pos: [1, 2]
      quality: "magic"
      item_level: 98
      visual_variant: "Horn"
    - name: "Large Charm of Mastery"
      pos: [2, 2]
      quality: "magic"
      item_level: 94
      visual_variant: "Obelisk"
    - name: "Valknut"
      pos: [3, 3]
      quality: "unique"
      item_level: 99
      visual_variant: "Custom"
    # Grand Charms
    - name: "Fiendish Grand Charm of Pestilence"
      pos: [0, 4]
      quality: "magic"
      item_level: 99
      visual_variant: "Monster"
    - name: "Grand Charm of Shock"
      pos: [1, 4]
      quality: "magic"
      item_level: 10
      visual_variant: "DNA"
    - name: "Grand Charm of Frost"
      pos: [2, 4]
      quality: "magic"
      item_level: 5
      visual_variant: "Eye"
    - name: "Conclave of Elements"
      pos: [3, 4]
      quality: "unique"
      item_level: 84
      visual_variant: "Custom"
```

