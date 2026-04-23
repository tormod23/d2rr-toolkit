# TC46 - Magic Socketed Armor (sock_unk=4)

## Summary

Tests parsing of a Magic quality socketed Ornate Plate with sock_unk=4 bits (NOT 20 as for Superior non-RW armor). Validates socket children of various types: gem, rare jewel, and rune.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Ornate Plate of Defiance (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `xar` (Ornate Plate)     |
| Quality           | 4 (Magic)                |
| Position          | Inventory                |
| Sockets           | 3                        |
| Defense           | 450                      |
| Durability        | 60/60                    |
| sock_unk          | 4 bits                   |

**In-Game Properties:**
- Poison Length Reduced by 75%

### Socket Children

| Slot | Item Code | Quality    | Name                |
|------|-----------|------------|---------------------|
| 1    | `gmm`     | -          | Amethyst            |
| 2    | `jew`     | 6 (Rare)   | Rune Talisman       |
| 3    | `r22`     | -          | Um Rune             |

**Rare Jewel "Rune Talisman" Properties:**
- +22% Enhanced Damage
- +56 to Attack Rating
- +51 Defense

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC46/OrnatePlate.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC46/OrnatePlate.d2s
```

