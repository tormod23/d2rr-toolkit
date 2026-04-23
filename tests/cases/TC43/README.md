# TC43 - Magic Small Charm with has_gfx=1 and has_class=1

## Summary

Tests parsing of a Magic Small Charm with both has_gfx=1 and has_class=1 set. Validates automod reading for a bf1=False item and the carry-chain formula for prefix/suffix resolution with the extra graphics bit.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

### Item 1 - Polarised Small Charm of the Icicle (iLvl 94)

| Field             | Value                    |
|-------------------|--------------------------|
| Item Code         | `cm1` (Small Charm)      |
| Quality           | 4 (Magic)                |
| Position          | Inventory (0,0)          |
| has_gfx           | 1                        |
| has_class          | 1                        |

**In-Game Properties:**
- +5% Fire Resist
- +4% Cold Resist
- Adds 4-6 Cold Damage
- Charm Weight 1

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC43/OnlyCharm.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC43/OnlyCharm.d2s
```

