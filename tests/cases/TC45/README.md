# TC45 - Spirit Runeword Shield (28-bit sock_unk)

## Summary

Tests parsing of a Spirit Monarch runeword shield with 28-bit sock_unk (4 bits socket count + 24 bits RW data). Validates RW display property decoding, socket children parsing, and confirms NO shield_unk(2) is read for RW shields.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Spirit Monarch (iLvl varies)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `uit` (Monarch)          |
| Quality           | 2 (Normal)               |
| Position          | Inventory                |
| Runeword          | Spirit                   |
| Sockets           | 4                        |
| Defense           | 144                      |
| Durability        | 86/86                    |
| sock_unk          | 28 bits (4+24)           |

**RW Display Properties:**
- +2 to All Skills
- +33% Faster Cast Rate
- +23% Faster Hit Recovery
- +250 Defense vs Missile
- +22 Vitality
- +69 Mana
- +5 Magic Absorb

### Socket Children

| Slot | Item Code | Name       |
|------|-----------|------------|
| 1    | `r07`     | Tal Rune   |
| 2    | `r10`     | Thul Rune  |
| 3    | `r09`     | Ort Rune   |
| 4    | `r11`     | Amn Rune   |

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC45/Spirit.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC45/Spirit.d2s
```

