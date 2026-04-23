# TC38 - Vanilla-Compatible Runeword (Insight) with 4 Rune Children (.d2s)

## Summary

This scenario tests a **vanilla-compatible runeword** - Insight (Ral+Tir+Tal+Sol) - socketed
into a **Thresher [E]** (Elite two-handed weapon). Unlike TC24 which tested Reimagined-specific
runewords (Glory, Revenge), TC38 uses a runeword that also exists in standard D2R.

- **File:** TestSorc.d2s
- **Mod:** D2R Reimagined
- **Character:** TestSorc (Sorceress, Level 1)
- **Gold (Inventory):** 0
- **Items:** 1 parent (Thresher) + 4 socket children (Ral, Tir, Tal, Sol runes)

### Key Verifications

- Total item count = **5** (1 parent + 4 socket children)
- Thresher: Normal quality, runeword + socketed
- Rune children: Ral, Tir, Tal, Sol (all socketed inside parent)
- Runeword name: "Insight" (determined by rune recipe)
- Durability: 146/250, Item Level: 82

### Runeword Display Properties

Runeword display properties are NOT stored per-item. The game computes them from
`runes.txt` at runtime. The display properties come from two sources:
1. **Runeword-level bonuses** (Insight recipe): Enhanced Damage, Bonus AR, MF,
   Critical Strike, Faster Cast Rate, Meditation Aura, All Attributes
2. **Individual rune bonuses**: Ral (+Fire Damage), Tir (+Mana after Kill),
   Tal (+Poison Damage), Sol (+Min Weapon Damage)

## Character Overview

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold (Inventory):** 0

## Inventory Items

| Slot       | Item Name              | Item Code | Base Type      | iLvl | Quality | Modification                |
|------------|------------------------|-----------|----------------|------|---------|-----------------------------|
| Inv (0,0)  | Insight                | `7s8`     | Thresher [E]   | 82   | Normal  | Runeword (4 sockets filled) |
| (child)    | Ral Rune               | `r08`     | -              | -    | -       | Socket child of Thresher    |
| (child)    | Tir Rune               | `r03`     | -              | -    | -       | Socket child of Thresher    |
| (child)    | Tal Rune               | `r07`     | -              | -    | -       | Socket child of Thresher    |
| (child)    | Sol Rune               | `r12`     | -              | -    | -       | Socket child of Thresher    |

## Item Details

### Insight - Thresher [E], Inventory (0,0)

- **Runeword:** Insight (Ral+Tir+Tal+Sol)
- **Base Type:** Thresher [E] (Elite, two-handed spear)
- **Quality:** Normal (base item)
- **Item Level:** 82
- **Sockets:** 4 (all filled)
- **Durability:** 146 of 250
- **Required Dexterity:** 118
- **Required Strength:** 152
- **Required Level:** 53

**Runeword Properties (displayed in-game):**

| Property                                  | Source       | runes.txt Ref      |
|-------------------------------------------|--------------|--------------------|
| Level 17 Meditation Aura When Equipped    | Runeword     | aura=Meditation    |
| +3 to Critical Strike (Oskill)            | Runeword     | oskill=Crit Strike |
| +35% Faster Cast Rate                     | Runeword     | cast2              |
| +216% Enhanced Weapon Damage              | Runeword     | dmg% 200-260       |
| +223% Bonus to Attack Rating              | Runeword     | att% 180-250       |
| +23% Chance Items Roll Magic or Better    | Runeword     | mag%               |
| +5 to All Attributes                      | Runeword     | all-stats          |
| +9 to Minimum Weapon Damage               | Sol rune     | (rune bonus)       |
| Adds 5-30 Weapon Fire Damage              | Ral rune     | (rune bonus)       |
| +75 Weapon Poison Damage over 5 Seconds   | Tal rune     | (rune bonus)       |
| +2 to Mana after each Kill                | Tir rune     | (rune bonus)       |

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

  item_count: 5          # 1 parent + 4 socket children
  jm_count: 1            # parent only; children inline after JM list

  items:
    - name: "Insight"
      base_type: "Thresher [E]"
      item_code: "7s8"
      location: "inventory"
      quality: "normal"
      item_level: 82
      runeword: true
      socketed: true
      socket_count: 4
      durability_max: 250
      durability_cur: 146
      runeword_name_by_recipe: "Insight"
      recipe: ["r08", "r03", "r07", "r12"]   # Ral + Tir + Tal + Sol
      magical_properties: []     # Normal quality weapon: no base ISC props
      runeword_properties: []    # Internal state slot only - display props from runes.txt

    - item_code: "r08"           # Ral rune
      parent: "7s8"

    - item_code: "r03"           # Tir rune
      location_id: 6
      parent: "7s8"

    - item_code: "r07"           # Tal rune
      location_id: 6
      parent: "7s8"

    - item_code: "r12"           # Sol rune
      location_id: 6
      parent: "7s8"

```

