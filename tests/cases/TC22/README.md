# TC22 - Runeword, +Max Damage, Assassin Claw

## Summary

Tests three critical untested code paths:
1. **Runeword item** - completely new parsing path (16-bit runeword ID + runeword mods at end)
2. **+X to Maximum Weapon Damage** (stat 22) - verifies stats 21/22 as hardcoded pair
3. **Assassin Claw** (class-restricted weapon) - tests class-specific weapon handling

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify runeword structure, stat 21/22 pair, class weapon handling.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0              C1              C2         C3
R0 [Highland]      [Scissors]      [Light Plate]
R1 [Highland]      [Scissors]      [Light Plate]
R2 [Highland]      [Scissors]      [Light Plate]
R3 [Highland]                      .
```

Items: 3 total (2 weapons + 1 runeword armor)

## Item Details

### Item 1: Blade of Conan - Position (0,0), Size 1x4, Unique
- **Base:** Highland Blade [E] (Elite)
- **Quality:** Unique
- **Item Level:** 99
- **Two-Hand Damage:** 253 to 465
- **Durability:** 144 / 250
- **Required Dexterity:** 104
- **Required Strength:** 171
- **Required Level:** 75
- **Properties:**
  - Level 9 Might Aura When Equipped
  - +2 to Barbarian Skill Levels
  - +31% Increased Attack Speed
  - +279% Enhanced Weapon Damage
  - +102 to Maximum Weapon Damage
  - +25% Deadly Strike
  - +10% Magic Resistance
  - +100% Extra Gold from Monsters
- **Note:** Highland Blade is a Sword, NOT blunt - no auto Undead bonus

### Item 2: Scissors Katar of Evisceration - Position (1,0), Size 1x3, Magic
- **Base:** Scissors Katar [N] (Normal)
- **Quality:** Magic
- **Item Level:** 99
- **One-Hand Damage:** 9 to 101
- **Durability:** 250 / 250
- **Required Dexterity:** 55
- **Required Strength:** 55
- **Required Level:** 65
- **Class Restriction:** Assassin Only
- **Properties:**
  - +84 to Maximum Weapon Damage
  - +2 to Wake of Fire (Assassin Only)

### Item 3: Revenge - Position (2,0), Size 2x3, **RUNEWORD**
- **Base:** Light Plate [N] (Normal)
- **Quality:** Normal (Runeword)
- **Runes:** Thul + Eld (2 sockets, both filled)
- **Item Level:** 99
- **Defense:** 92
- **Durability:** 56 / 60
- **Required Strength:** 41
- **Required Level:** 26
- **Properties (from Runeword):**
  - +1 to Sorceress Skill Levels
  - +15% Faster Cast Rate
  - +65 to Mana
  - +69% Mana Regeneration
  - +6% Magic Resistance
  - +30% Cold Resistance
  - +5 Life after each Kill
  - +3% to Experience Gained
  - +3 to Required Level
  - Socketed (2)


## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    - name: "Blade of Conan"
      pos: [0, 0]
      quality: "unique"
      item_level: 99
      durability_max: 250
      durability_current: 144
      properties:
        - "Level 9 Might Aura When Equipped"
        - "+2 to Barbarian Skill Levels"
        - "+31% Increased Attack Speed"
        - "+279% Enhanced Weapon Damage"
        - "+102 to Maximum Weapon Damage"
        - "+25% Deadly Strike"
        - "+10% Magic Resistance"
        - "+100% Extra Gold from Monsters"
    - name: "Scissors Katar of Evisceration"
      pos: [1, 0]
      quality: "magic"
      item_level: 99
      durability_max: 250
      durability_current: 250
      properties:
        - "+84 to Maximum Weapon Damage"
        - "+2 to Wake of Fire (Assassin Only)"
    - name: "Revenge"
      pos: [2, 0]
      quality: "runeword"
      runes: "ThulEld"
      item_level: 99
      defense: 92
      durability_max: 60
      durability_current: 56
      sockets: 2
      sockets_filled: 2
      properties:
        - "+1 to Sorceress Skill Levels"
        - "+15% Faster Cast Rate"
        - "+65 to Mana"
        - "+69% Mana Regeneration"
        - "+6% Magic Resistance"
        - "+30% Cold Resistance"
        - "+5 Life after each Kill"
        - "+3% to Experience Gained"
        - "+3 to Required Level"
```

