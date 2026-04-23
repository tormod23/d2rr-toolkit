# TC57 - D2I Write-Read Roundtrip: Single Item (Gheed's Fortune)

## Summary

First successful D2I write-read roundtrip test with the actual game. A single
Unique Grand Charm (Gheed's Fortune) was extracted from VikingBarbie.d2s (TC56 #21),
written into an empty Shared Stash via D2IWriter, and verified by loading in
D2R Reimagined. A second file was created in-game for byte-level comparison.

This TC proves that:
- The D2IWriter produces game-compatible binary output
- Item blobs extracted from D2S files are valid when written to D2I
- The item blob is **byte-identical** between our writer and the game's output
- Section 6 trailing metadata differs slightly (game updates tracking data)

## Files

| File | Description |
|------|-------------|
| `StressTest.d2i` | Written by D2RR Toolkit (item in Tab 0 / Section 0) |
| `StressTestValidate.d2i` | Written by D2R Reimagined in-game (item in Tab 5 / Section 4) |

## Character Overview

Item source: VikingBarbie (Sorceress, Level 100) from TC56.

## Item Details

### Gheed's Fortune (Unique Grand Charm)

| Field | Value |
|-------|-------|
| Item Code | `cm3` |
| Quality | 7 (Unique) |
| iLvl | 99 |
| has_gfx | 1 |
| Source Position (VikingBarbie) | Personal Stash (0,10) |
| Blob Size | 27 bytes |

## Byte-Level Comparison Results

| Aspect | Our File | Game File | Match |
|--------|----------|-----------|-------|
| File size | 583 bytes | 583 bytes | YES |
| Item blob (27 bytes) | `1000800005...e23f` | `1000800005...e23f` | **IDENTICAL** |
| Item section | Section 0 (Tab 0) | Section 4 (Tab 5) | Different tab (user placed in Tab 5) |
| Section 6 trailing data | Original template | Updated by game | Expected difference |

## Key Finding

The item binary blob is **byte-identical** between our D2IWriter output and the
game's native save. The only structural differences are:
1. Tab placement (user error - item was placed in Tab 5 instead of Tab 0)
2. Section 6 trailing metadata (game updates internal tracking data on save)

## CLI Reference

```yaml
parse: python -m d2rr_toolkit.cli parse tests/cases/TC57/StressTest.d2i
parse: python -m d2rr_toolkit.cli parse tests/cases/TC57/StressTestValidate.d2i
```

