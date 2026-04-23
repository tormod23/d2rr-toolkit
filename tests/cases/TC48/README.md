# TC48 - Complex Character with 5 Main Items + Sockets

## Summary

Tests parsing of a complex inventory with multiple item types: runeword, unique, magic, set (corrupted), and a Gem Bag. Validates inter-item padding (56 bits after Diamond Facet), stacked gem count, and corrupted set armor with socket children. 14 total items (5 main + 9 socket children).

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Call to Arms (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `7h7` (Poleaxe)          |
| Quality           | 2 (Normal)               |
| Position          | Inventory                |
| Runeword          | Call to Arms             |
| Sockets           | 5                        |

### Item 2 - Diamond Facet (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 7 (Unique)               |
| Position          | Inventory                |

### Item 3 - Small Charm (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `cm1` (Small Charm)      |
| Quality           | 4 (Magic)                |
| Position          | Inventory                |

### Item 4 - Gem Bag (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `bag` (Gem Bag)          |
| Position          | Inventory                |
| Stacked Gems      | 225                      |

### Item 5 - Panda's Jacket (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `uui` (Set Armor)        |
| Quality           | 5 (Set)                  |
| Position          | Inventory                |
| Corrupted         | Yes                      |
| Sockets           | 4                        |

**Tests:**
- Multiple runeword + set + unique + magic items in one file
- Inter-item padding (56 bits after Diamond Facet)
- Gem Bag parsing (stacked_gem=225)
- Corrupted set armor with socket children
- 14 total items (5 main + 9 socket children)

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC48/BigStats.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC48/BigStats.d2s
```

