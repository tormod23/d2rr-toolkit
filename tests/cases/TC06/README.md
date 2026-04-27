# TC06 - Shared Stash - 19 Items Showcase (Tab 1)

## Summary
This scenario serves as a wide-coverage "Item Showcase" for the "D2R Reimagined" Shared Stash. It contains 19 varied items exclusively in the first Shared Tab. This test case validates the parsing of various item classes (Unique Shields, Orbs, Set Armor, Jewelry) as well as tricky item states like Ethereal, Indestructible, and socketed items with children.

- **File:** ModernSharedStashSoftCoreV2.d2i
- **Format:** D2R v3.0 + Reimagined Mod (8-Section Layout)
- **Goal:** Verify the correct parsing of 19 items, including class-specific items (Sorceress/Warlock), Set bonuses, and filled sockets.

## Stash Overview (Visuals)

The Shared Stash consists of 8 functional sections. In this scenario, all items are located in Tab 1. Tabs 2-5, as well as the Gems, Materials, and Runes tabs, are empty.

### Shared Tab 1 (Items)
- **Status:** Contains 19 items.
- **Grid Size:** 16x13 (Reimagined Expanded Grid).
- **Coordinates:** 0-based (X, Y), where (0,0) is top-left.

## Tab 1 Inventory Grid (16x13)

   C0    C1    C2    C3    C4    C5    C6    C7    C8    C9    C10   C11   C12   C13   C14   C15

R0   [SpT] [SpT] [Rvl] [GCl] [HoL] [SpI] [TmR] [PoC] [PoC]  .     .     .     .     .     .     .
R1   [SpT] [SpT] [RPl] [OoC] [HoL] [SpI] [TmR] [PoC] [PoC] [SpW] [SpW]  .     .     .     .     .
R2   [SpT] [SpT] [JPl] [DWS] [TP ]  .     .     .     .    [SpW] [SpW]  .     .     .     .     .
R3   [WoE]  .     .     .     .     .     .     .     .    [SpW] [SpW]  .    [Ocu]  .    [SSk] [SSk]
R4   [WoE]  .     .     .     .     .     .     .     .    [SpW] [SpW]  .    [Ocu]  .     .     .
R5    .     .     .     .     .     .     .     .     .     .     .     .    [Ocu]  .     .     .
R6-10 .     .     .     .     .     .     .     .     .     .     .     .     .     .     .     .
R7    .     .     .     .     .     .     .    [DFS] [DFS]  .     .     .     .     .     .     .
R8    .     .     .     .     .     .     .    [DFS] [DFS]  .     .     .     .     .     .     .
R9    .     .     .     .     .     .     .    [DFS] [DFS]  .     .     .     .     .     .     .
R11   .     .     .     .     .     .     .     .     .     .     .     .     .     .     .    [SFa]
R12   .     .     .     .     .     .     .     .     .     .     .     .     .     .     .    [SoJ]


## Item List (Shared Tab 1)

| Code | Item Name | Position | Size | Quality |
|:-----|:----------|:---------|:-----|:--------|
| **SpT** | Spike Thorn (Blade Barrier) | (0, 0) | 2x3 | Unique |
| **WoE** | Worusk's End (Statue) | (0, 3) | 1x2 | Unique |
| **Rvl** | Full Rejuvenation Potion | (2, 0) | 1x1 | Normal |
| **RPl** | Rune Pliers | (2, 1) | 1x1 | Normal |
| **JPl** | Jewel Pliers | (2, 2) | 1x1 | Normal |
| **GCl** | Gem Cluster | (3, 0) | 1x1 | Normal |
| **OoC** | Orb of Conversion | (3, 1) | 1x1 | Normal |
| **DWS** | Deep Worldstone Shard | (3, 2) | 1x1 | Normal |
| **HoL** | Haven of Light (Heavenly Stone) | (4, 0) | 1x2 | Unique |
| **TP** | Scroll of Town Portal | (4, 2) | 1x1 | Normal |
| **SpI** | Spectral Image (Ghost Wand) | (5, 0) | 1x2 | Unique |
| **TmR** | Terminus Rod (Glowing Orb) | (6, 0) | 1x2 | Unique |
| **PoC** | Possessed Compendium | (7, 0) | 2x2 | Unique |
| **SpW** | Spirit Ward (Ward) | (9, 1) | 2x4 | Unique |
| **Ocu** | The Oculus (Swirling Crystal) | (12, 3) | 1x3 | Unique |
| **SSk** | Spiritseeker (Light Belt) | (14, 3) | 2x1 | Unique |
| **DFS** | Darkmage's Falling Star | (7, 7) | 2x3 | Set |
| **SFa** | Sapphire Facet (Jewel) | (15, 11) | 1x1 | Unique |
| **SoJ** | The Stone of Jordan (Ring) | (15, 12) | 1x1 | Unique |

## Item Highlight Details

### Spike Thorn (Unique Shield)
- **Quality:** Unique
- **Flags:** Identified, Socketed (3 Sockets visually)
- **Stats:** Level 29 Thorns Aura, +30% FHR, +150% Enhanced Defense.
- **Note:** Contains 3 Empty Sockets.

### Darkmage's Falling Star (Set Armor)
- **Quality:** Set
- **Flags:** Ethereal, Indestructible (Max Durability = 0)
- **Sockets:** 1 Empty Socket.
- **Stats:** Part of the Darkmage's Astral Projection set.

### Spirit Ward (Unique Ward)
- **Quality:** Unique
- **Flags:** Ethereal
- **Stats:** High block and defense bonuses.

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2i_shared_stash"
  mod: "D2R Reimagined"
  total_sections: 8
  grid_dimensions: [16, 13]

  tabs:
    - index: 0
      name: "Shared Tab 1"
      item_count: 19
      items:
        - name: "Spike Thorn"
          pos: [0, 0]
          quality: "unique"
          sockets: 3
        - name: "Worusk's End"
          pos: [0, 3]
          quality: "unique"
        - name: "Haven of Light"
          pos: [4, 0]
          quality: "unique"
        - name: "Possessed Compendium"
          pos: [7, 0]
          quality: "unique"
        - name: "Spirit Ward"
          pos: [9, 1]
          quality: "unique"
          is_ethereal: true
        - name: "Darkmage's Falling Star"
          pos: [7, 7]
          quality: "set"
          is_ethereal: true
          is_indestructible: true
        - name: "The Stone of Jordan"
          pos: [15, 12]
          quality: "unique"
    - index: 1
      name: "Shared Tab 2"
      item_count: 0
    - index: 2
      name: "Shared Tab 3"
      item_count: 0
    - index: 3
      name: "Shared Tab 4"
      item_count: 0
    - index: 4
      name: "Shared Tab 5"
      item_count: 0
    - index: 5
      name: "Gems"
      item_count: 0
    - index: 6
      name: "Materials"
      item_count: 0
    - index: 7
      name: "Runes"
      is_empty: true
