# TC44 - Three Items with Inter-Item Padding

## Summary

Tests parsing of three items in sequence with inter-item padding detection. The 56-bit gap after the Unique Jewel (with has_gfx=1) must be correctly identified and skipped. Validates sequential parsing of items with different quality types.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Diamond Facet (iLvl 99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 7 (Unique)               |
| Position          | Inventory (0,0)          |

### Item 2 - Small Charm (iLvl 94)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `cm1` (Small Charm)      |
| Quality           | 4 (Magic)                |
| Position          | Inventory (1,0)          |

### Item 3 - Magic Jewel (iLvl 99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 4 (Magic)                |
| Position          | Inventory (2,0)          |

**Tests:**
- Inter-item padding (56-bit gap after Unique Jewel with has_gfx=1)
- Multiple items with different quality types parsed sequentially

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC44/AllThree.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC44/AllThree.d2s
```

