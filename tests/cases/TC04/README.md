# TC04 - Empty Shared Stash

## Summary
This scenario validates the parsing of a completely empty Shared Stash file. It represents a stash with no items, no gold, and no materials across all available tabs.

- **File:** ModernSharedStashSoftCoreV2.d2i
- **Mod:** D2R Reimagined
- **Goal:** Verify correct parsing of all stash tabs when they are completely empty.

## Stash Overview

The Shared Stash presents 8 functional areas in the game UI (5 item tabs + Gems, Materials, Runes). In this scenario, every slot is vacant.

**Parser note:** The parser reads 6 JM-based item tabs. The Gems, Materials, and Runes sections are stored in a separate trailing region of the file that is not yet parsed; they are always reported as 0 items.

### Shared Item Tabs 1-5
- **Status:** All five tabs are completely empty.
- **Grid Size:** 16x13 each (Expanded Reimagined Grid).

### Gems Tab
- **Status:** Empty. No stackable gems present.

### Materials Tab
- **Status:** Empty. No crafting materials or utility items present.

### Runes Tab
- **Status:** Empty. The dedicated rune display is entirely clear.

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2i_shared_stash"
  mod: "D2R Reimagined"
  grid_dimensions: [16, 13]

  # The parser reads 6 JM-based tabs. Gems/Materials/Runes are stored in a
  # separate trailing region and are not yet parsed (always 0 items).
  tabs:
    - name: "Shared Tab 1"
      item_count: 0
    - name: "Shared Tab 2"
      item_count: 0
    - name: "Shared Tab 3"
      item_count: 0
    - name: "Shared Tab 4"
      item_count: 0
    - name: "Shared Tab 5"
      item_count: 0
    - name: "Gems"
      item_count: 0
    - name: "Materials"
      item_count: 0
    - name: "Runes"
      item_count: 0

  gold: 0
```

