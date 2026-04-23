# TC30 - Shared Stash - Empty Tab Between Populated Tabs

## Summary

This scenario validates that the parser correctly handles a stash where an occupied tab is immediately followed by a completely empty tab, with further items present in a later tab. It is a targeted regression test for the tab-discovery algorithm's ability to navigate past empty tabs without losing its position.

- **File:** ModernSharedStashSoftCoreV2.d2i
- **Mod:** D2R Reimagined
- **Goal:** Verify correct item parsing when Tab 1 has items, Tab 2 is empty, and Tab 3 has items. All remaining tabs are empty.

## Stash Overview

Items are present in Tabs 1 and 3. Tab 2 is intentionally empty. Tabs 4 and 5 are empty. The Gems, Materials, and Runes tabs are empty. Gold: 0.

Grid dimensions per tab: 16 columns x 13 rows.

## Tab Contents

### Shared Tab 1
- **Full Rejuvenation Potion** - Position: (0,0)
- **Volcanic Small Charm** - Position: (1,0)

### Shared Tab 2
- *(empty - this is the critical gap being tested)*

### Shared Tab 3
- **Gnostic Ring Of The Wolf** - Position: (0,0)
- **Venomous Amulet** - Position: (1,0)

### Shared Tabs 4-5 / Gems / Materials / Runes
- *(all empty)*

## Item Details

### Shared Tab 1

1. **Full Rejuvenation Potion**
   - **Quality:** Normal (Consumable)
   - **Properties:** Restores 100% Life and Mana.

2. **Volcanic Small Charm**
   - **Quality:** Magic
   - **Item Level:** 99
   - **Properties:** +5% Lightning Resistance, +6% Fire Resistance.

### Shared Tab 3

1. **Gnostic Ring Of The Wolf**
   - **Quality:** Magic (Ring)
   - **Item Level:** 96
   - **Properties:** +5 to Iron Maiden (Necromancer only), +14 to Life.

2. **Venomous Amulet**
   - **Quality:** Magic (Amulet)
   - **Item Level:** 99
   - **Properties:** +3 to Poison and Bone Skills (Necromancer only).

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2i_shared_stash"
  mod: "D2R Reimagined"
  grid_dimensions: [16, 13]

  tabs:
    - name: "Shared Tab 1"
      item_count: 2
      items:
        - name: "Full Rejuvenation Potion"
          pos: [0, 0]
          quality: "normal"
        - name: "Volcanic Small Charm"
          pos: [1, 0]
          quality: "magic"
          item_level: 99
    - name: "Shared Tab 2"
      item_count: 0
    - name: "Shared Tab 3"
      item_count: 2
      items:
        - name: "Gnostic Ring Of The Wolf"
          pos: [0, 0]
          quality: "magic"
          item_level: 96
        - name: "Venomous Amulet"
          pos: [1, 0]
          quality: "magic"
          item_level: 99
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
  total_items: 4
```

