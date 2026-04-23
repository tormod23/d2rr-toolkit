# TC40 - Rare Jewel with Custom Graphics

## Summary

A Sorceress with a single item: **Rune Talisman** (Rare Jewel) with a
custom-graphics dye variant. Parser behaviour pinned by this fixture
is documented in `VERIFICATION_LOG.md`.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |
| Gold      | 0         |

## Inventory Contents

### Item 0 - Rune Talisman (98)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `jew` (Jewel)            |
| Quality           | 6 (Rare)                 |
| iLvl              | 98                       |
| Position          | Inventory (0,0)          |
| Custom Graphics   | Yes (dye variant)        |
| Rare Name         | Rune Talisman            |

**In-Game Properties:**
- +15 to Maximum Weapon Damage
- +25 Defense
- +20% Lightning Resistance

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC40/TestSorc.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC40/TestSorc.d2s
```

