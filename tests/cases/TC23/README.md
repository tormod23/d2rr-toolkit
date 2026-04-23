# TC23 - Weapon Damage Calibration, Low Quality, Shields

## Summary

Calibration test with **15 items** covering Normal and Low Quality weapons, shields,
and armor across multiple item types:

- 8 weapons (4 Normal, 4 Low Quality) including 1H, 2H, and throwing
- 3 shields (2 Normal, 1 Low Quality) with block chance values
- Wand with auto-mod "+50% Damage to Undead"
- Normal/Low Quality pairs of the same base type for comparison

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify correct parsing of Normal, Low Quality weapons, armor, and shields.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0          C1        C2         C3         C4         C5         C6        C7         C8         C9
R0 [LQ HAxe]  [ShortSw] [LrgAxe]  [LrgAxe]   [Spear]    .          [Buckler] .          [SmShield] .
R1 .           [ShortSw] .         .           [Spear]    .          [Buckler] .          [SmShield] .
R2 .           [ShortSw] .         .           [Spear]    .          [LQ TKnf][CrkWand]   [CrkSmSh]  .
R3 [DmgSkCap] .         .         .           .          .          .         .           .          .
R4 .           .         [2HSword]  [Dmg2HSw]  [Scimitar] [CrdScim]  .        .           .          .
R5 [LthGlvs]  .         [2HSword]  [Dmg2HSw]  [Scimitar] [CrdScim]  .        .           .          .
R6 .           .         [2HSword]  [Dmg2HSw]  .          .          .        .           .          .
R7 .           .         [2HSword]  [Dmg2HSw]  .          .          .        .           .          .
```

Items: 15 total

## Item Details

### === NORMAL QUALITY WEAPONS ===

### Item 1: Short Sword - Position (1,0), Size 1x3
- **Quality:** Normal
- **Item Level:** 6
- **One-Hand Damage:** 2 to 7
- **Durability:** 250 / 250
- **Attack Speed:** Normal

### Item 2: Large Axe - Position (2,0), Size 2x3
- **Quality:** Normal
- **Item Level:** 6
- **Two-Hand Damage:** 6 to 13
- **Durability:** 250 / 250
- **Required Strength:** 35
- **Attack Speed:** Fast

### Item 3: Spear - Position (4,0), Size 1x3
- **Quality:** Normal
- **Item Level:** 6
- **Two-Hand Damage:** 3 to 15
- **Durability:** 250 / 250
- **Required Dexterity:** 20
- **Attack Speed:** Normal

### Item 4: Two-Handed Sword - Position (2,4), Size 1x4
- **Quality:** Normal
- **Item Level:** 12
- **Two-Hand Damage:** 8 to 17
- **Durability:** 250 / 250
- **Required Dexterity:** 27
- **Required Strength:** 35
- **Attack Speed:** Normal

### Item 5: Scimitar - Position (4,5), Size 1x2
- **Quality:** Normal
- **Item Level:** 12
- **One-Hand Damage:** 2 to 6
- **Durability:** 250 / 250
- **Required Dexterity:** 21
- **Attack Speed:** Fast

### === LOW QUALITY WEAPONS ===

### Item 6: Low Quality Hand Axe - Position (0,0), Size 1x1
- **Quality:** Low Quality
- **Item Level:** 2
- **One-Hand Damage:** 2 to 4
- **Durability:** 54 / 82
- **Attack Speed:** Normal
- **Note:** Normal Hand Axe = 3-6 damage, 28 max dur. Low = 75% damage -> 2-4, dur ~ [(28-1)/3] = 9... but actual shows 82? Investigate!

### Item 7: Damaged Two-Handed Sword - Position (3,4), Size 1x4
- **Quality:** Low Quality
- **Item Level:** 9
- **Two-Hand Damage:** 6 to 12
- **Durability:** 67 / 82
- **Required Dexterity:** 27
- **Required Strength:** 35
- **Attack Speed:** Normal
- **Note:** Normal 2H Sword = 8-17 damage. Low = 75% -> 6-12.75 -> 6-12. [matches]

### Item 8: Crude Scimitar - Position (5,5), Size 1x2
- **Quality:** Low Quality
- **Item Level:** 6
- **One-Hand Damage:** 1 to 4
- **Durability:** 63 / 82
- **Required Dexterity:** 21
- **Attack Speed:** Fast
- **Note:** Normal Scimitar = 2-6 damage. Low = 75% -> 1.5-4.5 -> 1-4. [matches]

### Item 9: Low Quality Throwing Knife - Position (6,2), Size 1x1
- **Quality:** Low Quality
- **Item Level:** 1
- **Throw Damage:** 3 to 6
- **One-Hand Damage:** 1 to 2
- **Quantity:** 325 / 350
- **Required Dexterity:** 21
- **Attack Speed:** Fast
- **Replenishes Quantity:** Yes
- **Note:** Throwing weapon - uses Quantity instead of Durability!

### Item 10: Cracked Wand - Position (7,2), Size 1x1
- **Quality:** Low Quality
- **Item Level:** 1
- **One-Hand Damage:** 1 to 3
- **Durability:** 53 / 82
- **Attack Speed:** Normal
- **Auto-mod:** +50% Damage to Undead (wand inherent property)
- **Note:** Wand has auto-mod from ItemTypes.txt (inherent wand property).

### === NORMAL QUALITY ARMOR / SHIELDS ===

### Item 11: Buckler - Position (6,0), Size 1x2
- **Quality:** Normal
- **Item Level:** 6
- **Defense:** 6
- **Chance to Block:** 20%
- **Durability:** 12 / 12
- **Required Strength:** 12

### Item 12: Small Shield - Position (8,0), Size 1x2
- **Quality:** Normal
- **Item Level:** 6
- **Defense:** 10
- **Chance to Block:** 25%
- **Durability:** 16 / 16
- **Required Strength:** 22

### Item 13: Leather Gloves - Position (0,5), Size 1x1
- **Quality:** Normal
- **Item Level:** 6
- **Defense:** 3
- **Durability:** 12 / 12
- **Note:** Same item type as TC08 - serves as cross-reference anchor.

### === LOW QUALITY ARMOR / SHIELDS ===

### Item 14: Cracked Small Shield - Position (8,2), Size 1x1
- **Quality:** Low Quality
- **Item Level:** 5
- **Defense:** 6
- **Chance to Block:** 25%
- **Durability:** 2 / 5
- **Required Strength:** 22
- **Note:** Normal Small Shield = defense 8-12, dur 16. Low = 75% defense, dur ~ [(16-1)/3]=5. [matches]

### Item 15: Damaged Skull Cap - Position (0,3), Size 1x1
- **Quality:** Low Quality
- **Item Level:** 5
- **Defense:** 7
- **Durability:** 2 / 5
- **Required Strength:** 15
- **Note:** Normal Skull Cap = defense 8-11, dur 18. Low = 75% -> 6-8, dur ~ [(18-1)/3]=5. [matches]


## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    # Normal Weapons
    - name: "Short Sword"
      code: "ssd"
      pos: [1, 0]
      quality: "normal"
      item_level: 6
      damage_min: 2
      damage_max: 7
      durability_max: 250
      durability_current: 250
    - name: "Large Axe"
      code: "lax"
      pos: [2, 0]
      quality: "normal"
      item_level: 6
      damage_min: 6
      damage_max: 13
      durability_max: 250
      durability_current: 250
    - name: "Spear"
      code: "spr"
      pos: [4, 0]
      quality: "normal"
      item_level: 6
      damage_min: 3
      damage_max: 15
      durability_max: 250
      durability_current: 250
    - name: "Two-Handed Sword"
      code: "2hs"
      pos: [2, 4]
      quality: "normal"
      item_level: 12
      damage_min: 8
      damage_max: 17
      durability_max: 250
      durability_current: 250
    - name: "Scimitar"
      code: "scm"
      pos: [4, 5]
      quality: "normal"
      item_level: 12
      damage_min: 2
      damage_max: 6
      durability_max: 250
      durability_current: 250
    # Low Quality Weapons
    - name: "Low Quality Hand Axe"
      code: "hax"
      pos: [0, 0]
      quality: "low_quality"
      item_level: 2
      damage_min: 2
      damage_max: 4
      durability_max: 82
      durability_current: 54
    - name: "Damaged Two-Handed Sword"
      code: "2hs"
      pos: [3, 4]
      quality: "low_quality"
      item_level: 9
      damage_min: 6
      damage_max: 12
      durability_max: 82
      durability_current: 67
    - name: "Crude Scimitar"
      code: "scm"
      pos: [5, 5]
      quality: "low_quality"
      item_level: 6
      damage_min: 1
      damage_max: 4
      durability_max: 82
      durability_current: 63
    - name: "Low Quality Throwing Knife"
      code: "tkf"
      pos: [6, 2]
      quality: "low_quality"
      item_level: 1
      throw_damage_min: 3
      throw_damage_max: 6
      damage_min: 1
      damage_max: 2
      quantity: 325
      quantity_max: 350
    - name: "Cracked Wand"
      code: "wnd"
      pos: [7, 2]
      quality: "low_quality"
      item_level: 1
      damage_min: 1
      damage_max: 3
      durability_max: 82
      durability_current: 53
      auto_mod: "+50% Damage to Undead"
    # Normal Shields
    - name: "Buckler"
      code: "buc"
      pos: [6, 0]
      quality: "normal"
      item_level: 6
      defense: 6
      block_chance: 20
      durability_max: 12
      durability_current: 12
    - name: "Small Shield"
      code: "sml"
      pos: [8, 0]
      quality: "normal"
      item_level: 6
      defense: 10
      block_chance: 25
      durability_max: 16
      durability_current: 16
    # Normal Armor
    - name: "Leather Gloves"
      code: "lgl"
      pos: [0, 5]
      quality: "normal"
      item_level: 6
      defense: 3
      durability_max: 12
      durability_current: 12
    # Low Quality Armor/Shields
    - name: "Cracked Small Shield"
      code: "sml"
      pos: [8, 2]
      quality: "low_quality"
      item_level: 5
      defense: 6
      block_chance: 25
      durability_max: 5
      durability_current: 2
    - name: "Damaged Skull Cap"
      code: "skp"
      pos: [0, 3]
      quality: "low_quality"
      item_level: 5
      defense: 7
      durability_max: 5
      durability_current: 2
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```

