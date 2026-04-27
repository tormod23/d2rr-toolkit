# TC39 - Socketed Unique Weapon with Socket Children (Unique + Rare Jewel)

## Summary

A Sorceress with a single item: **Blade of Ali Baba** (Unique Tulwar [EX]), socketed
with two Jewels - one Unique (Spinel Facet) and one Rare (Rune Eye). This TC verifies:

- Unique Weapon parsing (quality=7) with socket flag
- Socket children detection (location_id=6) for inline child items
- Unique Jewel and Rare Jewel as socket children
- Property parsing across parent and children
- JM-count=1 (parent only), parser finds 3 total items (parent + 2 children)

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |
| Gold      | 0         |

## Inventory Contents

### Item 0 - Blade of Ali Baba (99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `9fc` (Tulwar [EX])     |
| Quality           | 7 (Unique)               |
| iLvl              | 99                       |
| Position          | Inventory (0,0)          |
| Socketed          | Yes (2 sockets)          |
| Durability        | 202/250                  |

**In-Game Properties (BASE, before socketing):**
- +91% Enhanced Weapon Damage
- +7 to Dexterity
- +15 to Mana
- +2% Extra Gold from Monsters (Based on Character Level)
- +1% Chance Items Roll Magic or Better (Based on Character Level)
- Socketed (2)

**Parsed Properties:**

| stat_id | name                      | value | notes                        |
|---------|---------------------------|-------|------------------------------|
| 2       | dexterity                 | 7     |                              |
| 9       | maxmana                   | 15    |                              |
| 17      | item_maxdamage_percent    | 91    | Enhanced Damage (paired)     |
| 18      | item_mindamage_percent    | 91    | Paired with stat 17          |
| 97      | item_nonclassskill        | 1     | param=449, Hidden Charm Passive |
| 239     | item_find_gold_perlevel   | 20    | Per-level gold find           |
| 240     | item_find_magic_perlevel  | 8     | Per-level magic find          |

### Item 1 - Spinel Facet (99) - Socket Child

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 7 (Unique)               |
| iLvl              | 99                       |
| Location          | 6 (in socket)            |
| GFX Index         | 4 (Red Dye Jewel)        |

**In-Game Properties:**
- +40% Enhanced Weapon Damage
- +50 to Attack Rating
- (Red Dye Jewel)

**Parsed Properties:**

| stat_id | name                      | value | notes                        |
|---------|---------------------------|-------|------------------------------|
| 17      | item_maxdamage_percent    | 40    | Enhanced Damage (paired)     |
| 18      | item_mindamage_percent    | 40    | Paired with stat 17          |
| 19      | tohit                     | 50    | Attack Rating                |

### Item 2 - Rune Eye (98) - Socket Child (Rare Jewel)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 6 (Rare)                 |
| iLvl              | 98                       |
| Location          | 6 (in socket)            |
| rare_name_id1     | 85                       |
| rare_name_id2     | 190                      |
| Affix IDs         | 1220, 1031, 1088, 11     |

**In-Game Properties:**
- +8 to Minimum Weapon Damage
- +4 to Maximum Weapon Damage
- +6 to Energy
- +15% to All Resistances
- (Blue Dye Jewel)

**Parsed Properties:**

| stat_id | name                      | value | notes                            |
|---------|---------------------------|-------|----------------------------------|
| 1       | energy                    | 6     |                                  |
| 21      | mindamage                 | 8     | +8 min damage                    |
| 22      | maxdamage                 | 4     | +4 max damage                    |
| 23      | secondary_mindamage       | 8     | Reimagined duplicate of min dmg  |
| 24      | secondary_maxdamage       | 4     | Reimagined duplicate of max dmg  |
| 39      | fireresist                | 15    | Part of "+15% All Res"           |
| 41      | lightresist               | 15    | Part of "+15% All Res"           |
| 43      | coldresist                | 15    | Part of "+15% All Res"           |
| 45      | poisonresist              | 15    | Part of "+15% All Res"           |
| 159     | item_throw_mindamage      | 8     | Reimagined duplicate (throw)     |
| 160     | item_throw_maxdamage      | 4     | Reimagined duplicate (throw)     |

**Note:** stat_id=448 (unknown, >435) terminates the property list. 11 of ~12+
properties are captured. The unknown stat is a Reimagined extension.

## Combined In-Game Display (After Socketing)

The in-game tooltip shows combined stats from parent + both children:
- +131% Enhanced Weapon Damage (91 base + 40 facet)
- +8 to Minimum Weapon Damage
- +4 to Maximum Weapon Damage
- +50 to Attack Rating
- +7 to Dexterity
- +6 to Energy
- +15 to Mana
- +15% to All Resistances
- +2% Extra Gold from Monsters (Based on Character Level)
- +1% Chance Items Roll Magic or Better (Based on Character Level)
- Socketed (2)

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC39/TestSorc.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC39/TestSorc.d2s
```
