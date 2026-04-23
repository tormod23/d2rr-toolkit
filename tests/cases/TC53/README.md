# TC53 - Mixed Inventory: Runeword Armor + Jewels + Weapons

## Summary

A Sorceress with 22 items including a runeword armor (4 rune children), a runeword
weapon (2 rune children), multiple jewels of varying quality, and simple Normal
weapons/armor. Serves as a wide-coverage integration test for mixed item types
in a single character file.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | TestSorc  |
| Class     | Sorceress |
| Level     | 1         |

## Inventory Contents

- Superior Archon Plate (uhn), socketed with 4x Ist runes - runeword armor
- Light Plate (ltp), Normal quality with 2 rune children
- War Staff (7s8), Normal quality
- 8 Jewels: Magic (q=4), Rare (q=6), Unique (q=7) - various properties
- Short Sword, Small Charm, Buckler, Large Axe, Small Shield - Normal quality items

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC53/SchreibTest.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC53/SchreibTest.d2s
```

