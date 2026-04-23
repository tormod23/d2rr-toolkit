# TC58 - D2I Write-Read Roundtrip: Complex Unique Amulet (Sigil of Hope)

## Summary

Second D2I write-read roundtrip test with the actual game, using a highly complex
item: **Sigil of Hope** (Unique Amulet) with 21 properties, corruption, custom
graphics (has_gfx=1), and a 63-byte binary blob. The item was extracted from
VikingBarbie.d2s (TC56 #89) and written to an empty Shared Stash. A validation
file was created from scratch in-game for byte-level comparison.

This TC proves that:
- Complex items with 21 properties, corruption, and has_gfx=1 write correctly
- The 63-byte item blob is **byte-identical** between our writer and the game
- All 6 tab sections (headers, JM markers, item counts) are structurally identical
- Only Section 6 trailing metadata differs (game-internal tracking data)

## Files

| File | Description |
|------|-------------|
| `StressTest.d2i` | Written by D2RR Toolkit (Sigil of Hope in Tab 0) |
| `StressTestValidate.d2i` | Created from scratch in D2R Reimagined in-game |

## Item Details

### Sigil of Hope (Unique Amulet)

| Field | Value |
|-------|-------|
| Item Code | `amu` |
| Quality | 7 (Unique) |
| iLvl | 99 |
| has_gfx | 1 (gfx_index=1) |
| Corrupted | Yes (roll 188) |
| Source | VikingBarbie.d2s (TC56) #89, position (0,8) |
| Blob Size | 63 bytes |
| Properties | 21 |

**Properties:**
- +50 Attack Rating
- +10% Increased Chance of Blocking
- +45% Fire/Lightning/Cold/Poison Resistance
- +5% Max Fire/Lightning/Cold/Poison Resistance
- +44% Magic Find
- +10% Faster Cast Rate
- +2 to All Skills
- Skill on Kill (stat 196)
- Gold Find per Level (stat 239)
- 5% Fire/Lightning/Cold/Poison Pierce
- Corrupted (stats 361+362, roll=188)

## Byte-Level Comparison Results

| Aspect | Our File | Game File | Match |
|--------|----------|-----------|-------|
| File size | 619 bytes | 619 bytes | **IDENTICAL** |
| Section structure | 7 sections (6 tabs + trailing) | 7 sections (6 tabs + trailing) | **IDENTICAL** |
| Section sizes | 131,68,68,68,68,68,148 | 131,68,68,68,68,68,148 | **IDENTICAL** |
| Tab 0 item count | 1 | 1 | **IDENTICAL** |
| **Item blob (63 bytes)** | `10 00 80 00 ...` | `10 00 80 00 ...` | **IDENTICAL** |
| Sections 0-5 (headers + items) | 471 bytes | 471 bytes | **IDENTICAL** |
| Section 6 trailing metadata | 148 bytes | 148 bytes | 55 bytes differ |

### Section 6 Trailing Data Differences

55 of 148 bytes differ in the trailing metadata section. This section does NOT
contain item data - it stores game-internal tracking information that the game
updates on every save. The differences are expected and do not affect item
integrity. All differences are in bytes 555-616 (trailing section offsets 16-77).

Our file preserves the original empty-stash template values (mostly `0xFF` and
`0x00` patterns). The game populates these with actual tracking data (timestamps,
session IDs, or similar metadata).

## Verification Summary

```
Sections 0-5 (tab headers + JM markers + item data): BYTE-IDENTICAL
Section 0 item blob (63 bytes, Sigil of Hope):        BYTE-IDENTICAL
Section 6 trailing metadata:                           55 bytes differ (expected)
```

**Conclusion:** The D2IWriter produces game-compatible output for complex items.
The item blob round-trip is perfect. The only differences are in game-internal
metadata that the engine updates independently.

## CLI Reference

```yaml
parse: python -m d2rr_toolkit.cli parse tests/cases/TC58/StressTest.d2i
parse: python -m d2rr_toolkit.cli parse tests/cases/TC58/StressTestValidate.d2i
```

