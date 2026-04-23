# TC41 - Magic Jewel with has_gfx=1

## Summary

Tests parsing of a Magic quality Jewel that has custom graphics (has_gfx=1). Validates the gfx_extra carry-chain formula for resolving prefix and suffix IDs when the extra graphics bit is present.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Jewel "of Hope" (iLvl 99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 4 (Magic)                |
| Position          | Inventory (0,0)          |
| has_gfx           | 1                        |
| has_class          | 0                        |

**In-Game Properties:**
- +13 to Life (stat maxhp=13)

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC41/EasyJewel.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC41/EasyJewel.d2s
```

