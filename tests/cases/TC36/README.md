# TC36 - Full Set (Sigon's Complete Steel - All 6 Pieces Equipped) (.d2s)

## Summary

This scenario tests parsing of **Set items** when all pieces of a set are equipped on
the character body. All 6 pieces of *Sigon's Complete Steel* are worn at the same time.
The key goal is to verify that per-item partial set bonus property lists are correctly
merged into each item's properties.

- **File:** TestABC.d2s
- **Mod:** D2R Reimagined
- **Character:** TestABC (Barbarian, Level 42)
- **Goal:** Verify correct parsing of all 6 set pieces and per-item bonus lists.

### Key Verifications
- All 6 items are Set quality, equipped on the character body
- Item count = exactly 6
- Per-item partial bonus properties (2-item, 3-item tiers) are merged into each item
- Sigon's Sabot has 4 properties: base (Cold Resist, FRW) +
  2-item bonus (+50 AR) + 3-item bonus (+50% MF)
- Sigon's Guard has exactly 3 properties and no per-item partial bonuses

### Global Set Bonuses
The global set bonuses (e.g. "+10% Life Stolen per Hit (2 Items)") are NOT stored per
item. They are applied at runtime by the game engine. The parser reads only what is
stored per item.

## Character Overview

- **Name:** TestABC
- **Class:** Barbarian
- **Level:** 42
- **Gold (Inventory):** 0

## Equipped Items (All at Body)

| Slot     | Item Name          | Item Code | Base Type       | iLvl |
|----------|--------------------|-----------|-----------------|------|
| Head (1) | Sigon's Visor      | `ghm`     | Great Helm [N]  | 99   |
| Torso (3)| Sigon's Shelter    | `gth`     | Gothic Plate [N]| 99   |
| Shield(5)| Sigon's Guard      | `tow`     | Tower Shield [N]| 99   |
| Belt (8) | Sigon's Wrap       | `hbl`     | Plated Belt [N] | 99   |
| Boots (9)| Sigon's Sabot      | `hbt`     | Greaves [N]     | 99   |
| Gloves(10)| Sigon's Gage      | `hgl`     | Gauntlets [N]   | 99   |

## Item Details

### Sigon's Visor - Great Helm [N], Slot: Head

- **Defense:** 60 (in-game; base 35 + +25 Defense property)
- **Durability:** 38 of 40
- **Required Strength:** 63
- **Required Level:** 6
- **Properties (base + 2-item bonus):**
  - +30 to Mana
  - +25 Defense
  - +8 to Attack Rating (Per Character Level) *(2-item bonus)*

### Sigon's Shelter - Gothic Plate [N], Slot: Torso

- **Defense:** 170 (in-game; base 136 * 1.25 Enhanced Defense)
- **Durability:** 45 of 55
- **Required Strength:** 70
- **Required Level:** 6
- **Properties (base + 2-item bonus):**
  - +25% Enhanced Defense
  - +30% Lightning Resistance
  - Attacker Takes Damage of 20 *(2-item bonus)*

### Sigon's Guard - Tower Shield [N], Slot: Shield

- **Defense:** 23
- **Chance to Block:** 24%
- **Durability:** 59 of 60
- **Required Strength:** 75
- **Required Level:** 6
- **Properties (base only, no per-item partial bonuses):**
  - +1 to All Skills
  - 20% Increased Chance of Blocking
- **Note:** This set piece has no per-item partial bonus properties.

### Sigon's Wrap - Plated Belt [N], Slot: Belt

- **Defense:** 10 (base; in-game shows higher with active set bonuses)
- **Durability:** 12 of 24
- **Required Strength:** 60
- **Required Level:** 6
- **Properties (base + 2-item bonus):**
  - +20 to Life
  - +20% Fire Resistance
  - +2 Defense (Per Character Level) *(2-item bonus)*

### Sigon's Sabot - Greaves [N], Slot: Boots

- **Defense:** 13 (base)
- **Durability:** 20 of 24
- **Required Strength:** 70
- **Required Level:** 6
- **Properties (base + 2-item + 3-item bonuses):**
  - +40% Cold Resistance
  - +20% Faster Run/Walk Speed
  - +50 to Attack Rating *(2-item bonus)*
  - +50% Chance Items Roll Magic or Better *(3-item bonus)*
- **Note:** Only set piece with two active bonus tiers (mask bits 0+1 set).

### Sigon's Gage - Gauntlets [N], Slot: Gloves

- **Defense:** 14
- **Durability:** 13 of 24
- **Required Strength:** 60
- **Required Level:** 6
- **Properties (base + 2-item bonus):**
  - +10 to Strength
  - +20 to Attack Rating
  - +30% Increased Attack Speed *(2-item bonus)*

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2s_character"
  mod: "D2R Reimagined"
  character:
    name: "TestABC"
    class: "Barbarian"
    level: 42
    gold: 0

  items:
    - name: "Sigon's Visor"
      base_type: "Great Helm [N]"
      item_code: "ghm"
      location: "equipped"
      equipped_slot: 1
      quality: "set"
      item_level: 99
      defense_display: 35
      durability_current: 38
      durability_max: 40
      properties:
        - {stat_id: 9,   value: 30, name: "maxmana"}          # +30 to Mana (base)
        - {stat_id: 31,  value: 25, name: "armorclass"}       # +25 Defense (base)
        - {stat_id: 224, value: 16, name: "item_tohit_perlevel"} # +8 AR/level (2-item bonus)

    - name: "Sigon's Shelter"
      base_type: "Gothic Plate [N]"
      item_code: "gth"
      location: "equipped"
      equipped_slot: 3
      quality: "set"
      item_level: 99
      defense_display: 136
      durability_current: 45
      durability_max: 55
      properties:
        - {stat_id: 16,  value: 25, name: "item_armor_percent"}   # +25% Enh. Def (base)
        - {stat_id: 41,  value: 30, name: "lightresist"}          # +30% Lightning Res (base)
        - {stat_id: 78,  value: 20, name: "item_attackertakesdamage"} # ATD 20 (2-item bonus)

    - name: "Sigon's Guard"
      base_type: "Tower Shield [N]"
      item_code: "tow"
      location: "equipped"
      equipped_slot: 5
      quality: "set"
      item_level: 99
      defense_display: 23
      durability_current: 59
      durability_max: 60
      property_count: 3        # EXACTLY 3 - mask=0 means NO bonus lists
      properties:
        - {stat_id: 20,  value: 20,  name: "toblock"}           # 20% block
        - {stat_id: 97,  value: 1,   param: 449, name: "item_nonclassskill"} # Hidden Charm Passive
        - {stat_id: 127, value: 1,   name: "item_allskills"}    # +1 All Skills

    - name: "Sigon's Wrap"
      base_type: "Plated Belt [N]"
      item_code: "hbl"
      location: "equipped"
      equipped_slot: 8
      quality: "set"
      item_level: 99
      defense_display: 10
      durability_current: 12
      durability_max: 24
      properties:
        - {stat_id: 7,   value: 20, name: "maxhp"}           # +20 Life (base)
        - {stat_id: 39,  value: 20, name: "fireresist"}      # +20% Fire Res (base)
        - {stat_id: 214, value: 16, name: "item_armor_perlevel"} # +2 Def/level (2-item bonus)

    - name: "Sigon's Sabot"
      base_type: "Greaves [N]"
      item_code: "hbt"
      location: "equipped"
      equipped_slot: 9
      quality: "set"
      item_level: 99
      defense_display: 13
      durability_current: 20
      durability_max: 24
      property_count: 4        # Base(2) + 2-item bonus(1) + 3-item bonus(1)
      properties:
        - {stat_id: 43,  value: 40, name: "coldresist"}        # +40% Cold Res (base)
        - {stat_id: 96,  value: 20, name: "item_fastermovevelocity"} # +20% FRW (base)
        - {stat_id: 19,  value: 50, name: "tohit"}             # +50 AR (2-item bonus)
        - {stat_id: 80,  value: 50, name: "item_magicbonus"}   # +50% MF (3-item bonus)

    - name: "Sigon's Gage"
      base_type: "Gauntlets [N]"
      item_code: "hgl"
      location: "equipped"
      equipped_slot: 10
      quality: "set"
      item_level: 99
      defense_display: 14
      durability_current: 13
      durability_max: 24
      properties:
        - {stat_id: 0,   value: 10, name: "strength"}           # +10 Strength (base)
        - {stat_id: 19,  value: 20, name: "tohit"}              # +20 AR (base)
        - {stat_id: 93,  value: 30, name: "item_fasterattackrate"} # +30% IAS (2-item bonus)
```

