# TC49 - Full Endgame Character (145 Items Stress Test)

## Summary

Stress test with a full endgame character containing 145 items total (125 JM items + 20 extra items including socket children and misc). Tests complete parsing of all quality types, multiple runewords, inter-item padding detection, and mercenary section handling. Zero garbage items expected.

## Character Overview

| Field     | Value     |
|-----------|-----------|
| Name      | MrLockhart|
| Class     | Warlock   |
| Level     | 98        |

## Inventory Contents

145 total items across inventory, equipped slots, stash, cube, and mercenary. Key items include:

### Equipped Runewords
- Spirit (shield)
- Call to Arms
- Grim Ward

### Notable Item Types
- Multiple quality types: Normal, Magic, Rare, Set, Unique
- Gems, Jewels, Charms, Orbs
- Gem Bag
- OnyxGrabber
- Horadric Cube

### Mercenary Section
- `jf` header with 3rd JM marker
- 25 mercenary items (10 equipped + 15 socketed)
- 10 JM-counted + 15 extra items after JM count

**Tests:**
- Full endgame character stress test (145 items, 0 garbage)
- All socket children correctly associated with parent items
- Inter-item padding detection across many items
- Mercenary section parsing (`jf` header with 3rd JM marker + extra items)
- 125 JM items + 20 extra items (socket children + misc)

## CLI Reference

```yaml
parse:   python -m d2rr_toolkit.cli parse tests/cases/TC49/MrLockhart.d2s
inspect: python -m d2rr_toolkit.cli inspect tests/cases/TC49/MrLockhart.d2s
```

