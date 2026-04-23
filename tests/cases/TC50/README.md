# TC50 - Unique Jewel: Diamond Facet (Isolated)

## Summary

A Sorceress with a single item: **Diamond Facet** (Unique Jewel) with custom graphics
(has_gfx=1). Tests Unique quality jewel parsing in isolation, including gfx_extra
carry-chain for unique_type_id resolution.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 0 - Diamond Facet (99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 7 (Unique)               |
| iLvl              | 99                       |
| Position          | Inventory (0,0)          |
| Custom Graphics   | Yes (has_gfx=1)          |

**In-Game Properties:**
- +10% Faster Cast Rate
- 6% Increased Chance of Blocking
- +9% to All Resistances
- +4% Physical Damage Reduction

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC50/DiamondFacet.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC50/DiamondFacet.d2s
```

