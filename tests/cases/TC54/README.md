# TC54 - Jewel Verification: 7 Loose Jewels (Rare + Unique)

## Summary

A Sorceress with 7 loose jewels in inventory - 4 Rare and 2 Unique quality plus
1 Magic. Used as a verification counterpart to TC25, testing that jewel parsing
produces consistent results across different save files containing similar items.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

- 4x Rare Jewels (q=6) with varying affix counts (5-10 properties each)
- 2x Unique Jewels (q=7) with 6 properties each
- 1x Magic Jewel (q=4) with 3 properties

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC54/VerifySorc.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC54/VerifySorc.d2s
```
