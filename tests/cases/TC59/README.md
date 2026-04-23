# TC59 - D2I Write-Read Roundtrip: Socketed Item with Children (Ragnarok + 4 Facets)

## Summary

A **Ragnarok** (Unique Bone Visage) with 4 socketed Heaven Facets,
extracted from VikingBarbie's save (TC56 #107) and written into a
fresh Shared Stash at position (0,0). The game validation file was
created from scratch in D2R Reimagined. Parser and writer behaviour
pinned by this fixture is documented in `VERIFICATION_LOG.md`.

## Files

| File | Description |
|------|-------------|
| `StressTest.d2i` | Written by D2RR Toolkit (Ragnarok + 4 Facets in Tab 0, position (0,0)) |
| `StressTestValidate2.d2i` | Created from scratch in D2R Reimagined in-game |

## Item Details

### Ragnarok (Unique Helm) - Parent Item

| Field | Value |
|-------|-------|
| Item Code | `uhm` (Bone Visage) |
| Quality | 7 (Unique) |
| Corrupted | Yes (roll 186) |
| Enchanted | Yes (upgrade_medium = 3) |
| Sockets | 4 (all filled with Heaven Facets) |
| Source | VikingBarbie.d2s (TC56) #107 |

### Heaven Facets (*4) - Socket Children

| Field | Value |
|-------|-------|
| Item Code | `jew` |
| Quality | 7 (Unique) |
| Custom Graphics | Yes |

## CLI Reference

```yaml
parse: python -m d2rr_toolkit.cli parse tests/cases/TC59/StressTest.d2i
parse: python -m d2rr_toolkit.cli parse tests/cases/TC59/StressTestValidate2.d2i
```

