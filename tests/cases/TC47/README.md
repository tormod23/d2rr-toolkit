# TC47 - Set Armor with Unique Jewel Socket Child

## Summary

Tests parsing of a Set quality ethereal socketed armor (Darkmage's Falling Star) with a Unique Jewel (Diamond Facet) as its socket child. Validates Set bonus mask parsing, ethereal defense multiplier, and set_bonus_properties handling.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Darkmage's Falling Star (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `uhn` (Boneweave)        |
| Quality           | 5 (Set)                  |
| Position          | Inventory                |
| Ethereal          | Yes                      |
| Sockets           | 1                        |
| Defense           | 2034                     |
| Indestructible    | Yes                      |
| bonus_mask        | 5                        |

**In-Game Properties:**
- +168% Enhanced Defense
- Ethereal
- Indestructible

### Socket Children

| Slot | Item Code | Quality      | Name          |
|------|-----------|--------------|---------------|
| 1    | `jew`     | 7 (Unique)   | Diamond Facet |

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC47/SetSocket.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC47/SetSocket.d2s
```

