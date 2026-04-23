# TC52 - Unique Amulet: Eye of Kahn (Isolated)

## Summary

A Sorceress with a single item: **Eye of Kahn** (Unique Amulet). Tests Unique quality
amulet parsing in isolation, verifying property list decoding for a non-jewel
unique misc item.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 0 - Eye of Kahn (99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `amu` (Amulet)           |
| Quality           | 7 (Unique)               |
| iLvl              | 99                       |
| Position          | Inventory (0,0)          |

**In-Game Properties:**
- +3 to All Skills
- +100% Enhanced Defense
- +20% Faster Cast Rate
- +10% Faster Hit Recovery
- +99 to Life
- +99 to Mana
- All Resistances +20%

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC52/EyeOfKahn.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC52/EyeOfKahn.d2s
```

