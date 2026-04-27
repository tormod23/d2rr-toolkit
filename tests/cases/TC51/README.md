# TC51 - Unique Jewel: Spinel Facet (Isolated)

## Summary

A Sorceress with a single item: **Spinel Facet** (Unique Jewel) with custom graphics
(has_gfx=1). Tests Unique quality jewel parsing with a different gfx_extra value
than TC50, verifying the carry-chain formula produces the correct unique_type_id.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 0 - Spinel Facet (99)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 7 (Unique)               |
| iLvl              | 99                       |
| Position          | Inventory (0,0)          |
| Custom Graphics   | Yes (has_gfx=1)          |

**In-Game Properties:**
- +40% Enhanced Weapon Damage
- +50 to Attack Rating

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC51/SpinelFacet.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC51/SpinelFacet.d2s
```
