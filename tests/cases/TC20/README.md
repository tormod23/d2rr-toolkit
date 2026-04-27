# TC20 - Hardcoded Damage Pairs + Weapon Verification

## Summary

Tests damage stat pairs (lightning, poison), Unique charms, and a weapon item
with known damage values.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify lightning/poison hardcoded stat groups, weapon damage fields.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0          C1          C2       C3          C4          C5       C6
R0 [GC-Light]  [GC-Pois]   [SC-Lt]  [GC-Unique] [LC-Unique] [SC-Def] [WS]
R1 [GC-Light]  [GC-Pois]            [GC-Unique] [LC-Unique]          [WS]
R2 [GC-Light]  [GC-Pois]            [GC-Unique]                      [WS]
```

Items: 2 Grand Charms + 1 Small Charm + 1 Unique Grand Charm + 1 Unique Large Charm + 1 Small Charm + 1 War Sword = 7 total

## Item Details

### Item 1: Static Grand Charm of Shock - Position (0,0), Size 1x3
- **Quality:** Magic
- **Item Level:** 5
- **Properties:**
  - Adds 4-12 Weapon Lightning Damage

### Item 2: Grand Charm of Pestilence - Position (1,0), Size 1x3
- **Quality:** Magic
- **Item Level:** 98
- **Properties:**
  - Adds 39-47 Weapon Poison Damage over 4 Seconds

### Item 3: Small Charm of Lightning - Position (2,0), Size 1x1
- **Quality:** Magic
- **Item Level:** 98
- **Properties:**
  - Adds 4-7 Weapon Lightning Damage

### Item 4: Conclave of Elements - Position (3,0), Size 1x3, Unique
- **Quality:** Unique
- **Item Level:** 84
- **Properties:**
  - Adds 63-511 Weapon Fire Damage
  - Adds 63-511 Weapon Lightning Damage
  - Adds 63-511 Weapon Cold Damage

### Item 5: Valknut - Position (4,0), Size 1x2, Unique
- **Quality:** Unique
- **Item Level:** 99
- **Properties:**
  - +9% to Dexterity
  - +10% to Energy
  - +8 to all Attributes
  - +9% to Experience Gained

### Item 6: Small Charm of Defense - Position (5,0), Size 1x1
- **Quality:** Magic
- **Item Level:** 98
- **Properties:**
  - +13 Defense

### Item 7: War Sword (Paralyzing) - Position (6,0), Size 1x3
- **Quality:** Magic
- **Item Level:** 99
- **One-Hand Damage:** 8-20
- **Durability:** 250 / 250
- **Required Dexterity:** 45
- **Required Strength:** 71
- **Required Level:** 56
- **Properties:**
  - Slows Target by 21%


## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    - name: "Static Grand Charm of Shock"
      pos: [0, 0]
      quality: "magic"
      item_level: 5
      properties:
        - "Adds 4-12 Weapon Lightning Damage"
    - name: "Grand Charm of Pestilence"
      pos: [1, 0]
      quality: "magic"
      item_level: 98
      properties:
        - "Adds 39-47 Weapon Poison Damage over 4 Seconds"
    - name: "Small Charm of Lightning"
      pos: [2, 0]
      quality: "magic"
      item_level: 98
      properties:
        - "Adds 4-7 Weapon Lightning Damage"
    - name: "Conclave of Elements"
      pos: [3, 0]
      quality: "unique"
      item_level: 84
      properties:
        - "Adds 63-511 Weapon Fire Damage"
        - "Adds 63-511 Weapon Lightning Damage"
        - "Adds 63-511 Weapon Cold Damage"
    - name: "Valknut"
      pos: [4, 0]
      quality: "unique"
      item_level: 99
      properties:
        - "+9% to Dexterity"
        - "+10% to Energy"
        - "+8 to all Attributes"
        - "+9% to Experience Gained"
    - name: "Small Charm of Defense"
      pos: [5, 0]
      quality: "magic"
      item_level: 98
      properties:
        - "+13 Defense"
    - name: "War Sword (Paralyzing)"
      pos: [6, 0]
      quality: "magic"
      item_level: 99
      durability_max: 250
      durability_current: 250
      damage: "8-20"
      properties:
        - "Slows Target by 21%"
```
