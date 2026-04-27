# TC42 - Unique Jewel (Diamond Facet) with has_gfx=1

## Summary

Tests parsing of a Unique quality Diamond Facet with has_gfx=1. Validates the carry-chain uid formula (uid*2+hc-2) and correct property alignment after the gfx_extra bit.

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
| has_gfx           | 1                        |
| has_class          | 0                        |

**In-Game Properties:**
- +10% Faster Cast Rate
- 6% Chance to Block
- +9% All Resistances
- +4% Physical Damage Reduced

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC42/UniqueJewel.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC42/UniqueJewel.d2s
```
