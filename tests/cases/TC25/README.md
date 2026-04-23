# TC25 - Loose Jewels (Rare/Magic/Unique)

## Summary

Test with **7 loose (not socketed) jewels** in the inventory covering different
quality types (Rare, Unique, Magic) and graphic color variants.

Key targets:
1. **Rare Jewels** - variable number of affixes across 5 Rare jewels
2. **Graphic color variants** - 6 different jewel colors (Blue, Orange, Pink, Green, Red)
3. **Property validation** - known stat values for cross-reference

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify correct parsing of jewels across all quality types and color variants.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0          C1          C2          C3          C4          C5          C6
R0 [DeathEye]  [ShadowEye] [WinterFac] [HavocWhrl] [GhoulHrt]  [HavocEye]  [JewlWrath]
```

Items: 7 total (all 1x1 jewels in row 0)

## Item Details

### Item 1: Death Eye - Position (0,0), Rare, Color Blue
- **Code:** jew
- **Quality:** Rare (quality=6)
- **Item Level:** 98
- **Color:** Blue (gfx variant)
- **Required Level:** 35
- **Properties:**
  - +9 to Maximum Weapon Damage
  - Replenish Life +2
  - +26% Fire Resistance

### Item 2: Shadow Eye - Position (1,0), Rare, Color Orange
- **Code:** jew
- **Quality:** Rare (quality=6)
- **Item Level:** 98
- **Color:** Orange (gfx variant)
- **Required Level:** 30
- **Properties:**
  - +13 to Maximum Weapon Damage
  - +17 to Mana
  - +27% Fire Resistance
  - +3% Chance Items Roll Magic or Better

### Item 3: Winter Facet - Position (2,0), Unique, Color Pink
- **Code:** jew
- **Quality:** Unique (quality=7)
- **Item Level:** 99
- **Color:** Pink (gfx variant)
- **Required Level:** 49
- **Properties:**
  - 100% Chance to Cast Level 37 Blizzard When You Die
  - Adds 24-38 Weapon Cold Damage
  - -3% to Enemy Cold Resistance
  - +4% to Cold Skill Damage

### Item 4: Havoc Whorl - Position (3,0), Rare, Color Green
- **Code:** jew
- **Quality:** Rare (quality=6)
- **Item Level:** 96
- **Color:** Green (gfx variant)
- **Required Level:** 58
- **Properties:**
  - +37% Enhanced Weapon Damage
  - Adds 5-8 Weapon Damage
  - +1 to Strength
  - +26% Lightning Resistance

### Item 5: Ghoul Heart - Position (4,0), Rare, Color Pink
- **Code:** jew
- **Quality:** Rare (quality=6)
- **Item Level:** 81
- **Color:** Pink (gfx variant)
- **Required Level:** 58
- **Properties:**
  - +35% Enhanced Weapon Damage
  - Adds 4-20 Weapon Fire Damage
  - +20 to Mana
  - +24% Cold Resistance

### Item 6: Havoc Eye - Position (5,0), Rare, Color Green
- **Code:** jew
- **Quality:** Rare (quality=6)
- **Item Level:** 98
- **Color:** Green (gfx variant)
- **Required Level:** 33
- **Properties:**
  - +53 to Attack Rating
  - +40 Weapon Poison Damage over 2 seconds
  - +3% Chance Items Roll Magic or Better

### Item 7: Jewel of Wrath - Position (6,0), Magic, Color Red
- **Code:** jew
- **Quality:** Magic (quality=4)
- **Item Level:** 99
- **Color:** Red (gfx variant)
- **Required Level:** 11
- **Properties:**
  - +9 to Maximum Weapon Damage


## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    - name: "Death Eye"
      code: "jew"
      pos: [0, 0]
      quality: "rare"
      item_level: 98
      color: "Blue"
      properties:
        - "+9 to Maximum Weapon Damage"
        - "Replenish Life +2"
        - "+26% Fire Resistance"
    - name: "Shadow Eye"
      code: "jew"
      pos: [1, 0]
      quality: "rare"
      item_level: 98
      color: "Orange"
      properties:
        - "+13 to Maximum Weapon Damage"
        - "+17 to Mana"
        - "+27% Fire Resistance"
        - "+3% Chance Items Roll Magic or Better"
    - name: "Winter Facet"
      code: "jew"
      pos: [2, 0]
      quality: "unique"
      item_level: 99
      color: "Pink"
      properties:
        - "100% Chance to Cast Level 37 Blizzard When You Die"
        - "Adds 24-38 Weapon Cold Damage"
        - "-3% to Enemy Cold Resistance"
        - "+4% to Cold Skill Damage"
    - name: "Havoc Whorl"
      code: "jew"
      pos: [3, 0]
      quality: "rare"
      item_level: 96
      color: "Green"
      properties:
        - "+37% Enhanced Weapon Damage"
        - "Adds 5-8 Weapon Damage"
        - "+1 to Strength"
        - "+26% Lightning Resistance"
    - name: "Ghoul Heart"
      code: "jew"
      pos: [4, 0]
      quality: "rare"
      item_level: 81
      color: "Pink"
      properties:
        - "+35% Enhanced Weapon Damage"
        - "Adds 4-20 Weapon Fire Damage"
        - "+20 to Mana"
        - "+24% Cold Resistance"
    - name: "Havoc Eye"
      code: "jew"
      pos: [5, 0]
      quality: "rare"
      item_level: 98
      color: "Green"
      properties:
        - "+53 to Attack Rating"
        - "+40 Weapon Poison Damage over 2 seconds"
        - "+3% Chance Items Roll Magic or Better"
    - name: "Jewel of Wrath"
      code: "jew"
      pos: [6, 0]
      quality: "magic"
      item_level: 99
      color: "Red"
      properties:
        - "+9 to Maximum Weapon Damage"
  total_items: 7
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```

