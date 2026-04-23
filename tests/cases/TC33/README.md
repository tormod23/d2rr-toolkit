# TC33 - Weapon ISC-Parsing - Melee + Throwing Weapons (.d2s)

## Summary

This scenario is the definitive test for weapon property parsing. It covers both melee
weapons (War Swords) and throwing weapons (Flying Knife, Battle Darts) across all quality
tiers - Normal, Magic, Rare, and Unique - plus socketed and ethereal variants.

- **File:** TestSorc.d2s
- **Mod:** D2R Reimagined
- **Character:** TestSorc (Sorceress, Level 1)
- **Goal:** Verify correct property parsing for all weapon types and qualities.

### Key Verifications
- Normal, Magic, Rare, and Unique melee weapons
- Enhanced Damage stat pairing
- Throwing weapons with quantity across all quality levels
- Socketed weapons (empty and filled)
- Ethereal weapons

## Character Overview

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold:** 0

## Inventory Contents

### Row 0-2 (Melee Weapons - War Swords)

| Pos | Item | Quality | Notes |
|-----|------|---------|-------|
| (0,0) | War Sword [N] | Normal | Baseline: dur only, no properties |
| (1,0) | War Sword [N] | Normal Socketed(3) | Empty sockets, +4 sock bits |
| (2,0) | Gemmed War Sword [N] | Normal Socketed(3) | 'NefEthIth' runes |
| (3,0) | Ferocious War Sword [N] of Evisceration | Magic | +156% ED, +57 max dmg |
| (4,0) | Ferocious War Sword [N] of the Bat | Magic Ethereal | +217% ED, +5% ML |
| (5,0) | Shadow Gutter (War Sword [N]) | Rare | Many properties incl. fire dmg |
| (6,0) | Culwen's Point (War Sword [N]) | Unique | +1 Skills, 20 IAS, 20 FHR, 119% ED |

### Row 3-5 (Throwing Weapons - Battle Darts / Flying Knife)

| Pos | Item | Quality | Notes |
|-----|------|---------|-------|
| (0,3) | Flying Knife [E] | Normal | qty 350/350, Replenishes Quantity |
| (1,3) | Battle Dart [X] | Normal Socketed(2) | Empty sockets |
| (2,3) | Gemmed Battle Dart [X] | Normal Socketed(2) | 'IoLum' runes |
| (3,3) | Cruel Battle Dart [X] of Swiftness | Magic | +294% ED, +30% IAS |
| (4,3) | Soul Hew (Battle Dart [X]) | Rare | +175% ED, Prevent Monster Heal |
| (5,3) | Deathbit (Battle Dart [X]) | Unique | +191% ED, +370 AR, 5% ML, 7% LL |

## Item Details

### Melee Weapons

1. **War Sword [N]** - Position: (0,0)
   - **Quality:** Normal
   - **Item Level:** 99
   - **Durability:** 166 Of 250
   - **One-Hand Damage:** 8 to 20
   - **Required Dexterity:** 45
   - **Required Strength:** 71
   - **Properties:** *(none)*

2. **War Sword [N]** - Position: (1,0)
   - **Quality:** Normal
   - **Item Level:** 99
   - **Durability:** 156 Of 250
   - **Sockets:** 3 (empty)
   - **Properties:** *(none)*

3. **Gemmed War Sword [N]** - Position: (2,0)
   - **Quality:** Normal
   - **Item Level:** 99
   - **Durability:** 204 Of 250
   - **Sockets:** 3 (Nef, Eth, Ith)
   - **Runeword:** 'NefEthIth' (not a valid runeword - no runeword bonus)
   - **Properties:**
     - +9 to Maximum Weapon Damage
     - -25% Target Defense
     - Knockback

4. **Ferocious War Sword [N] of Evisceration** - Position: (3,0)
   - **Quality:** Magic
   - **Item Level:** 99
   - **Durability:** 250 Of 250
   - **Required Level:** 45
   - **Properties:**
     - +156% Enhanced Weapon Damage
     - +57 to Maximum Weapon Damage

5. **Ferocious War Sword [N] of the Bat** - Position: (4,0)
   - **Quality:** Magic, Ethereal
   - **Item Level:** 99
   - **Durability:** 250 Of 250
   - **Required Level:** 51
   - **Ethereal:** Cannot Be Repaired
   - **Properties:**
     - +217% Enhanced Weapon Damage
     - +5% Mana stolen per hit

6. **Shadow Gutter** - Position: (5,0)
   - **Base Type:** War Sword [N]
   - **Quality:** Rare
   - **Item Level:** 99
   - **Durability:** 308 Of 308
   - **Required Level:** 55
   - **Properties:**
     - +1 to Barbarian Skill Levels
     - +71% Enhanced Weapon Damage
     - +75 to Maximum Weapon Damage
     - Adds 92-134 Weapon Fire Damage
     - +4% Mana stolen per hit
     - +2 Life Per Hit

7. **Culwen's Point** - Position: (6,0)
   - **Base Type:** War Sword [N]
   - **Quality:** Unique
   - **Item Level:** 99
   - **Durability:** 146 Of 250
   - **Required Level:** 25
   - **Properties:**
     - +1 to All Skills
     - +20% Increased Attack Speed
     - +20% Faster Hit Recovery
     - +119% Enhanced Weapon Damage
     - +60 to Attack Rating
     - Poison Length Reduced by 50%

### Throwing Weapons

8. **Flying Knife [E]** - Position: (0,3)
   - **Quality:** Normal
   - **Item Level:** 96
   - **Quantity:** 350 Of 350
   - **Required Dexterity:** 141
   - **Required Strength:** 48
   - **Required Level:** 48
   - **Properties:**
     - Replenishes Quantity

9. **Battle Dart [X]** - Position: (1,3)
   - **Quality:** Normal
   - **Item Level:** 99
   - **Sockets:** 2 (empty)
   - **Properties:**
     - Replenishes Quantity

10. **Gemmed Battle Dart [X]** - Position: (2,3)
    - **Quality:** Normal
    - **Item Level:** 93
    - **Sockets:** 2 (Io, Lum)
    - **Properties:**
      - +10 to Vitality
      - +10 to Energy
      - Replenishes Quantity

11. **Cruel Battle Dart [X] of Swiftness** - Position: (3,3)
    - **Quality:** Magic
    - **Item Level:** 97
    - **Quantity:** 350 Of 350
    - **Required Level:** 69
    - **Properties:**
      - +30% Increased Attack Speed
      - +294% Enhanced Weapon Damage
      - Replenishes Quantity

12. **Soul Hew** - Position: (4,3)
    - **Base Type:** Battle Dart [X]
    - **Quality:** Rare
    - **Item Level:** 98
    - **Quantity:** 235 Of 350
    - **Required Level:** 51
    - **Properties:**
      - +175% Enhanced Weapon Damage
      - +1 to Maximum Weapon Damage (Based on Character Level)
      - +12 to Attack Rating (Based on Character Level)
      - Prevent Monster Heal
      - +12 to Strength
      - +9 Life after each Kill
      - Replenishes Quantity

13. **Deathbit** - Position: (5,3)
    - **Base Type:** Battle Dart [X]
    - **Quality:** Unique
    - **Item Level:** 99
    - **Quantity:** 350 Of 350
    - **Required Level:** 40
    - **Properties:**
      - +191% Enhanced Weapon Damage
      - +370 to Attack Rating
      - +5% Mana stolen per hit
      - +7% Life stolen per hit
      - +20% Deadly Strike
      - Replenishes Quantity

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
    # === Melee Weapons (War Swords) ===
    - name: "War Sword"
      location: "inventory"
      pos: [0, 0]
      quality: "normal"
      item_level: 99
      durability_current: 166
      durability_max: 250
      properties: []

    - name: "War Sword"
      location: "inventory"
      pos: [1, 0]
      quality: "normal"
      item_level: 99
      durability_current: 156
      durability_max: 250
      sockets: 3
      socket_contents: []
      properties: []

    - name: "Gemmed War Sword"
      location: "inventory"
      pos: [2, 0]
      quality: "normal"
      item_level: 99
      durability_current: 204
      durability_max: 250
      sockets: 3
      socket_contents: ["r04 (Nef)", "r05 (Eth)", "r06 (Ith)"]
      properties:
        - "+9 to Maximum Weapon Damage"
        - "-25% Target Defense"
        - "Knockback"

    - name: "Ferocious War Sword of Evisceration"
      location: "inventory"
      pos: [3, 0]
      quality: "magic"
      item_level: 99
      durability_current: 250
      durability_max: 250
      properties:
        - "+156% Enhanced Weapon Damage"
        - "+57 to Maximum Weapon Damage"

    - name: "Ferocious War Sword of the Bat"
      location: "inventory"
      pos: [4, 0]
      quality: "magic"
      item_level: 99
      ethereal: true
      durability_current: 250
      durability_max: 250
      properties:
        - "+217% Enhanced Weapon Damage"
        - "+5% Mana stolen per hit"

    - name: "Shadow Gutter"
      base_type: "War Sword [N]"
      location: "inventory"
      pos: [5, 0]
      quality: "rare"
      item_level: 99
      durability_current: 52
      durability_max: 250
      properties:
        - "+1 to Barbarian Skill Levels"
        - "+71% Enhanced Weapon Damage"
        - "+75 to Maximum Weapon Damage"
        - "Adds 92-134 Weapon Fire Damage"
        - "+4% Mana stolen per hit"
        - "+2 Life Per Hit"

    - name: "Culwen's Point"
      base_type: "War Sword [N]"
      location: "inventory"
      pos: [6, 0]
      quality: "unique"
      item_level: 99
      durability_current: 146
      durability_max: 250
      properties:
        - "+1 to All Skills"
        - "+20% Increased Attack Speed"
        - "+20% Faster Hit Recovery"
        - "+119% Enhanced Weapon Damage"
        - "+60 to Attack Rating"
        - "Poison Length Reduced by 50%"

    # === Throwing Weapons ===
    - name: "Flying Knife"
      base_type: "Flying Knife [E]"
      location: "inventory"
      pos: [0, 3]
      quality: "normal"
      item_level: 96
      quantity_current: 350
      quantity_max: 350
      properties:
        - "Replenishes Quantity"

    - name: "Battle Dart"
      base_type: "Battle Dart [X]"
      location: "inventory"
      pos: [1, 3]
      quality: "normal"
      item_level: 99
      sockets: 2
      socket_contents: []
      properties:
        - "Replenishes Quantity"

    - name: "Gemmed Battle Dart"
      base_type: "Battle Dart [X]"
      location: "inventory"
      pos: [2, 3]
      quality: "normal"
      item_level: 93
      sockets: 2
      socket_contents: ["r16 (Io)", "r17 (Lum)"]
      properties:
        - "+10 to Vitality"
        - "+10 to Energy"
        - "Replenishes Quantity"

    - name: "Cruel Battle Dart of Swiftness"
      base_type: "Battle Dart [X]"
      location: "inventory"
      pos: [3, 3]
      quality: "magic"
      item_level: 97
      quantity_current: 350
      quantity_max: 350
      properties:
        - "+30% Increased Attack Speed"
        - "+294% Enhanced Weapon Damage"
        - "Replenishes Quantity"

    - name: "Soul Hew"
      base_type: "Battle Dart [X]"
      location: "inventory"
      pos: [4, 3]
      quality: "rare"
      item_level: 98
      quantity_current: 235
      quantity_max: 350
      properties:
        - "+175% Enhanced Weapon Damage"
        - "+1 to Maximum Weapon Damage (Based on Character Level)"
        - "+12 to Attack Rating (Based on Character Level)"
        - "Prevent Monster Heal"
        - "+12 to Strength"
        - "+9 Life after each Kill"
        - "Replenishes Quantity"

    - name: "Deathbit"
      base_type: "Battle Dart [X]"
      location: "inventory"
      pos: [5, 3]
      quality: "unique"
      item_level: 99
      quantity_current: 350
      quantity_max: 350
      properties:
        - "+191% Enhanced Weapon Damage"
        - "+370 to Attack Rating"
        - "+5% Mana stolen per hit"
        - "+7% Life stolen per hit"
        - "+20% Deadly Strike"
        - "Replenishes Quantity"
```

