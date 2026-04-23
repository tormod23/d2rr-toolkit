# TC34 - Low/Superior Quality Items + Set Weapons (.d2s)

## Summary

This scenario is a multi-purpose calibration test targeting several open verification items:
Low/Superior quality armor and weapons, Set quality weapons (spears, orbs, daggers), Rare
spear (spr) and scimitar (scm) with ISC properties, and a socketed Superior weapon.

- **File:** TestSorc.d2s
- **Mod:** D2R Reimagined
- **Character:** TestSorc (Sorceress, Level 1)
- **Goal:** Verify correct parsing for Low Quality and Superior items in both armor and
  weapons, Set weapon structure with bonus property lists, and Rare weapon parsing.

### Key Verifications
- Low Quality armor and weapons (melee + throwing)
- Superior armor and weapons
- Set weapons with per-item bonus properties
- Rare Spear and Scimitar
- Socketed Superior Club

## Character Overview

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold (Inventory):** 0
- **Gold (Stash):** 0

## Inventory Contents

### Row 0 (Armor + Weapons at y=0)

| Pos   | Item                              | Quality  | Notes                        |
|-------|-----------------------------------|----------|------------------------------|
| (0,0) | Superior Leather Armor [N]        | Superior | +11% Max Durability, iLvl 1  |
| (2,0) | Cracked Leather Armor [N]         | Low      | Reduced stats, iLvl 2        |
| (4,0) | Crude Leather Armor [N]           | Low      | Reduced stats, iLvl 2        |
| (6,0) | Skull Goad (Rare Spear [N])       | Rare     | iLvl 86, 3 properties        |
| (8,0) | Warlord's Pike [N] (Talonrage's Fury) | Set  | iLvl 73, set bonus mask      |

### Row 3 (Boots at y=3)

| Pos   | Item                   | Quality  | Notes                              |
|-------|------------------------|----------|------------------------------------|
| (0,3) | Superior Boots [N]     | Superior | +9% ED, +14% Max Durability, iLvl 1 |
| (2,3) | Crude Boots [N]        | Low      | Reduced stats, iLvl 2              |
| (4,3) | Low Quality Boots [N]  | Low      | Reduced stats, iLvl 1              |

### Row 5 (Weapons and Misc at y=5)

| Pos   | Item                                       | Quality  | Notes                              |
|-------|--------------------------------------------|----------|------------------------------------|
| (0,5) | Javelin [N]                                | Normal   | Replenishes Qty, qty 350/350       |
| (1,5) | Cracked Javelin [N]                        | Low      | Throwing, qty 350/350, iLvl 1      |
| (2,5) | Low Quality Javelin [N]                    | Low      | Throwing, qty 350/350, iLvl 1      |
| (3,5) | Superior Hand Axe [N]                      | Superior | +1 Max Dmg, +2 AR, iLvl 4          |
| (4,5) | Superior Hand Axe [N]                      | Superior | +1 Max Dmg, +2 AR, iLvl 4 (copy)  |
| (5,5) | Superior Club [N]                          | Superior | +12% Max Dur, +50% vs Undead, Socketed(1) |
| (6,5) | Damaged Club [N]                           | Low      | Reduced stats, iLvl 1              |
| (7,5) | Viper Thirst (Rare Scimitar [N])           | Rare     | iLvl 90, 4 properties              |
| (8,5) | Tal Rasha's Lidless Eye (Tal Rasha's Wrappings) | Set | iLvl 99, Swirling Crystal [X], Sorceress Only |
| (9,5) | Dagger of Vashna (Legacy of Vashna)        | Set      | iLvl 97, Peignard [X]              |

## Item Details

### Low Quality Armor

1. **Cracked Leather Armor [N]** - Position: (2,0)
   - **Quality:** Low (Cracked)
   - **Item Level:** 2
   - **Defense:** 10
   - **Durability:** 3 of 7
   - **Required Strength:** 15
   - **Properties:** *(none beyond base stats)*

2. **Crude Leather Armor [N]** - Position: (4,0)
   - **Quality:** Low (Crude)
   - **Item Level:** 2
   - **Defense:** 12
   - **Durability:** 3 of 7
   - **Required Strength:** 15
   - **Properties:** *(none beyond base stats)*

3. **Crude Boots [N]** - Position: (2,3)
   - **Quality:** Low (Crude)
   - **Item Level:** 2
   - **Defense:** 2
   - **Durability:** 1 of 3
   - **Properties:** *(none beyond base stats)*

4. **Low Quality Boots [N]** - Position: (4,3)
   - **Quality:** Low
   - **Item Level:** 1
   - **Defense:** 2
   - **Durability:** 1 of 3
   - **Properties:** *(none beyond base stats)*

### Superior Armor

5. **Superior Leather Armor [N]** - Position: (0,0)
   - **Quality:** Superior
   - **Item Level:** 1
   - **Defense:** 16
   - **Durability:** 26 of 26
   - **Required Strength:** 15
   - **Properties:**
     - +11% Increased Maximum Durability

6. **Superior Boots [N]** - Position: (0,3)
   - **Quality:** Superior
   - **Item Level:** 1
   - **Defense:** 4
   - **Durability:** 13 of 13
   - **Properties:**
     - +9% Enhanced Defense
     - +14% Increased Maximum Durability

### Rare Spear (spr) - ISC Path Test

7. **Skull Goad** - Position: (6,0)
   - **Base Type:** Spear [N]
   - **Quality:** Rare
   - **Item Level:** 86
   - **Two-Hand Damage:** 11 to 58
   - **Durability:** 149 of 265
   - **Required Dexterity:** 20
   - **Required Level:** 63
   - **Properties:**
     - +288% Enhanced Weapon Damage
     - +8% Life Stolen Per Hit
     - +100% Hits Cause Monsters To Flee

### Set Weapon - Spear (spr), Set Bonus Mask

8. **Warlord's Pike** - Position: (8,0)
   - **Base Type:** Pike [N]
   - **Quality:** Set (Talonrage's Fury)
   - **Item Level:** 73
   - **Two-Hand Damage:** 33 to 151
   - **Durability:** 250 of 250
   - **Required Dexterity:** 45
   - **Required Strength:** 60
   - **Required Level:** 20
   - **Properties (main):**
     - +140% Enhanced Weapon Damage
     - Repairs 1 Durability in 20 Seconds
   - **Set Bonus Mask:** bit 1 set -> 1 bonus property list present

### Low Quality Weapons

9. **Cracked Javelin [N]** - Position: (1,5)
   - **Quality:** Low (Cracked)
   - **Item Level:** 1
   - **Throw Damage:** 4 to 10
   - **One-Hand Damage:** 1 to 3
   - **Quantity:** 350 of 350
   - **Properties:**
     - Replenishes Quantity

10. **Low Quality Javelin [N]** - Position: (2,5)
    - **Quality:** Low
    - **Item Level:** 1
    - **Throw Damage:** 4 to 10
    - **One-Hand Damage:** 1 to 3
    - **Quantity:** 350 of 350
    - **Properties:**
      - Replenishes Quantity

11. **Damaged Club [N]** - Position: (6,5)
    - **Quality:** Low (Damaged)
    - **Item Level:** 1
    - **One-Hand Damage:** 1 to 4
    - **Durability:** 72 of 82
    - **Properties:**
      - +50% Damage to Undead

### Normal Throwing Weapon

12. **Javelin [N]** - Position: (0,5)
    - **Quality:** Normal
    - **Item Level:** 1
    - **Throw Damage:** 6 to 14
    - **One-Hand Damage:** 1 to 5
    - **Quantity:** 350 of 350
    - **Properties:**
      - Replenishes Quantity

### Superior Weapons

13. **Superior Hand Axe [N]** - Position: (3,5)
    - **Quality:** Superior
    - **Item Level:** 4
    - **One-Hand Damage:** 3 to 7
    - **Durability:** 217 of 250
    - **Properties:**
      - +1 to Maximum Weapon Damage
      - +2 to Attack Rating

14. **Superior Hand Axe [N]** - Position: (4,5)
    - **Quality:** Superior
    - **Item Level:** 4
    - **One-Hand Damage:** 3 to 7
    - **Durability:** 217 of 250
    - **Properties:**
      - +1 to Maximum Weapon Damage
      - +2 to Attack Rating

15. **Superior Club [N]** - Position: (5,5)
    - **Quality:** Superior
    - **Item Level:** 2
    - **One-Hand Damage:** 1 to 6
    - **Durability:** 280 of 280
    - **Sockets:** 1 (empty)
    - **Properties:**
      - +12% Increased Maximum Durability
      - +50% Damage to Undead

### Rare Scimitar (scm) - ISC Path Test

16. **Viper Thirst** - Position: (7,5)
    - **Base Type:** Scimitar [N]
    - **Quality:** Rare
    - **Item Level:** 90
    - **One-Hand Damage:** 7 to 80
    - **Durability:** 250 of 250
    - **Required Dexterity:** 21
    - **Required Level:** 69
    - **Properties:**
      - +281% Enhanced Weapon Damage
      - +58 to Maximum Weapon Damage
      - Adds 49-173 Weapon Fire Damage
      - +7% Mana Stolen Per Hit

### Set Weapons - Exceptional Tier

17. **Tal Rasha's Lidless Eye** - Position: (8,5)
    - **Base Type:** Swirling Crystal [X]
    - **Quality:** Set (Tal Rasha's Wrappings)
    - **Item Level:** 99
    - **One-Hand Damage:** 18 to 42
    - **Durability:** 136 of 250
    - **Required Level:** 65
    - **Sorceress Only**
    - **Properties (main):**
      - +20 to Energy
      - +57 to Life
      - +77 to Mana
      - +25% Faster Cast Rate
      - +3 to Cold Mastery (Sorceress Only)
      - +4 to Lightning Mastery (Sorceress Only)
      - +3 to Fire Mastery (Sorceress Only)

18. **Dagger of Vashna** - Position: (9,5)
    - **Base Type:** Peignard [X]
    - **Quality:** Set (Legacy of Vashna)
    - **Item Level:** 97
    - **One-Hand Damage:** 41 to 88
    - **Durability:** 206 of 250
    - **Required Strength:** 25
    - **Required Level:** 30
    - **Properties (main):**
      - +75% Increased Attack Speed
      - +10% Faster Cast Rate
      - Adds 35-70 Weapon Damage

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2s_character"
  mod: "D2R Reimagined"
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
    gold: 0

  items:
    # === Low Quality Armor ===
    - name: "Cracked Leather Armor"
      location: "inventory"
      pos: [2, 0]
      quality: "low"
      item_level: 2
      defense: 10
      durability_current: 3
      durability_max: 7
      properties: []

    - name: "Crude Leather Armor"
      location: "inventory"
      pos: [4, 0]
      quality: "low"
      item_level: 2
      defense: 12
      durability_current: 3
      durability_max: 7
      properties: []

    - name: "Crude Boots"
      location: "inventory"
      pos: [2, 3]
      quality: "low"
      item_level: 2
      defense: 2
      durability_current: 1
      durability_max: 3
      properties: []

    - name: "Low Quality Boots"
      location: "inventory"
      pos: [4, 3]
      quality: "low"
      item_level: 1
      defense: 2
      durability_current: 1
      durability_max: 3
      properties: []

    # === Superior Armor ===
    - name: "Superior Leather Armor"
      location: "inventory"
      pos: [0, 0]
      quality: "superior"
      item_level: 1
      defense: 16
      durability_current: 26
      durability_max: 26
      properties:
        - "+11% Increased Maximum Durability"

    - name: "Superior Boots"
      location: "inventory"
      pos: [0, 3]
      quality: "superior"
      item_level: 1
      defense: 4
      durability_current: 13
      durability_max: 13
      properties:
        - "+9% Enhanced Defense"
        - "+14% Increased Maximum Durability"

    # === Rare Spear (spr) ===
    - name: "Skull Goad"
      base_type: "Spear [N]"
      location: "inventory"
      pos: [6, 0]
      quality: "rare"
      item_level: 86
      durability_current: 149
      durability_max: 265
      properties:
        - "+288% Enhanced Weapon Damage"
        - "+8% Life Stolen Per Hit"
        - "+100% Hits Cause Monsters To Flee"

    # === Set Weapon (Pike) ===
    - name: "Warlord's Pike"
      base_type: "Pike [N]"
      location: "inventory"
      pos: [8, 0]
      quality: "set"
      item_level: 73
      durability_current: 250
      durability_max: 250
      properties:
        - "+140% Enhanced Weapon Damage"
        - "Repairs 1 Durability in 20 Seconds"

    # === Normal Javelin ===
    - name: "Javelin"
      location: "inventory"
      pos: [0, 5]
      quality: "normal"
      item_level: 1
      quantity_current: 350
      quantity_max: 350
      properties:
        - "Replenishes Quantity"

    # === Low Quality Throwing Weapons ===
    - name: "Cracked Javelin"
      location: "inventory"
      pos: [1, 5]
      quality: "low"
      item_level: 1
      quantity_current: 350
      quantity_max: 350
      properties:
        - "Replenishes Quantity"

    - name: "Low Quality Javelin"
      location: "inventory"
      pos: [2, 5]
      quality: "low"
      item_level: 1
      quantity_current: 350
      quantity_max: 350
      properties:
        - "Replenishes Quantity"

    # === Superior Weapons ===
    - name: "Superior Hand Axe"
      location: "inventory"
      pos: [3, 5]
      quality: "superior"
      item_level: 4
      durability_current: 217
      durability_max: 250
      properties:
        - "+1 to Maximum Weapon Damage"
        - "+2 to Attack Rating"

    - name: "Superior Hand Axe"
      location: "inventory"
      pos: [4, 5]
      quality: "superior"
      item_level: 4
      durability_current: 217
      durability_max: 250
      properties:
        - "+1 to Maximum Weapon Damage"
        - "+2 to Attack Rating"

    - name: "Superior Club"
      location: "inventory"
      pos: [5, 5]
      quality: "superior"
      item_level: 2
      durability_current: 280
      durability_max: 280
      sockets: 1
      socket_contents: []
      properties:
        - "+12% Increased Maximum Durability"
        - "+50% Damage to Undead"

    # === Low Quality Melee Weapon ===
    - name: "Damaged Club"
      location: "inventory"
      pos: [6, 5]
      quality: "low"
      item_level: 1
      durability_current: 72
      durability_max: 82
      properties:
        - "+50% Damage to Undead"

    # === Rare Scimitar (scm) ===
    - name: "Viper Thirst"
      base_type: "Scimitar [N]"
      location: "inventory"
      pos: [7, 5]
      quality: "rare"
      item_level: 90
      durability_current: 250
      durability_max: 250
      properties:
        - "+281% Enhanced Weapon Damage"
        - "+58 to Maximum Weapon Damage"
        - "Adds 49-173 Weapon Fire Damage"
        - "+7% Mana Stolen Per Hit"

    # === Set Weapons (Exceptional) ===
    - name: "Tal Rasha's Lidless Eye"
      base_type: "Swirling Crystal [X]"
      location: "inventory"
      pos: [8, 5]
      quality: "set"
      item_level: 99
      durability_current: 136
      durability_max: 250
      properties:
        - "+20 to Energy"
        - "+57 to Life"
        - "+77 to Mana"
        - "+25% Faster Cast Rate"
        - "+3 to Cold Mastery (Sorceress Only)"
        - "+4 to Lightning Mastery (Sorceress Only)"
        - "+3 to Fire Mastery (Sorceress Only)"

    - name: "Dagger of Vashna"
      base_type: "Peignard [X]"
      location: "inventory"
      pos: [9, 5]
      quality: "set"
      item_level: 97
      durability_current: 206
      durability_max: 250
      properties:
        - "+75% Increased Attack Speed"
        - "+10% Faster Cast Rate"
        - "Adds 35-70 Weapon Damage"
```

