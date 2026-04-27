# TC05 - Shared Stash - Diverse Items across 5 Tabs

## Summary
This scenario validates the parsing of multiple items distributed across the first five Shared Tabs of the D2R Reimagined Shared Stash. It covers various item types (Elite weapons, Jewelry, Charms, Quest items, and Mod-specific items) and checks for specific flags like Ethereal status and Rare name generation.

- **File:** ModernSharedStashSoftCoreV2.d2i
- **Mod:** D2R Reimagined
- **Goal:** Verify correct item parsing across multiple tabs with mixed item properties (Ethereal, Magic/Rare/Unique qualities, and Reimagined-specific stats).

## Stash Overview

Items are present in Tabs 1 through 5. The Gems, Materials, and Runes tabs are empty.
Grid dimensions per tab: 16 columns x 13 rows.

## Tab Contents

### Shared Tab 1
- **Cryptic Axe (Ethereal)** - Position: (0,0)
- **Volcanic Small Charm** - Position: (15,4)

### Shared Tab 2
- **War Pike (Ethereal)** - Position: (2,2)
- **Nature's Peace (Unique Ring)** - Position: (8,0)
- **Uncontrolled Small Charm** - Position: (15,4)

### Shared Tab 3
- **Key of Destruction** - Position: (3,2)
- **Orb of Conversion** - Position: (9,7)

### Shared Tab 4
- **Eagle Eye (Rare Ring)** - Position: (0,0)
- **Chaos Mark (Rare Amulet)** - Position: (1,0)

### Shared Tab 5
- **Konnan's Maul (Unique Great Maul)** - Position: (0,0)

## Item Details

### Shared Tab 1
1. **Cryptic Axe (Ethereal)**
   - **Quality:** Normal (Tier [E])
   - **Ethereal:** Yes
   - **Properties:** Reimagined Classless Skill on weapon.
2. **Volcanic Small Charm**
   - **Quality:** Magic
   - **Properties:** +1 to Fire Skills.

### Shared Tab 2
1. **War Pike (Ethereal)**
   - **Quality:** Normal (Tier [E])
   - **Ethereal:** Yes
2. **Nature's Peace**
   - **Quality:** Unique (Ring)
   - **Properties:** Slain Monsters Rest in Peace, Prevent Monster Heal, Poison Resist +20-30%.
3. **Uncontrolled Small Charm**
   - **Quality:** Magic
   - **Properties:** +4% Lightning Resistance, +5% Fire Resistance.

### Shared Tab 3
1. **Key of Destruction**
   - **Quality:** Normal (Quest Item)
2. **Orb of Conversion**
   - **Quality:** Normal (Mod-specific Utility Item)

### Shared Tab 4
1. **Eagle Eye**
   - **Quality:** Rare (Ring)
2. **Chaos Mark**
   - **Quality:** Rare (Amulet)

### Shared Tab 5
1. **Konnan's Maul**
   - **Quality:** Unique (Great Maul)

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
        - name: "Cryptic Axe"
          pos: [0, 0]
          quality: "normal"
          is_ethereal: true
        - name: "Volcanic Small Charm"
          pos: [15, 4]
          quality: "magic"
    - name: "Shared Tab 2"
      item_count: 3
      items:
        - name: "War Pike"
          pos: [2, 2]
          quality: "normal"
          is_ethereal: true
        - name: "Nature's Peace"
          pos: [8, 0]
          quality: "unique"
        - name: "Uncontrolled Small Charm"
          pos: [15, 4]
          quality: "magic"
    - name: "Shared Tab 3"
      item_count: 2
      items:
        - name: "Key of Destruction"
          pos: [3, 2]
          quality: "normal"
        - name: "Orb of Conversion"
          pos: [9, 7]
          quality: "normal"
    - name: "Shared Tab 4"
      item_count: 2
      items:
        - name: "Eagle Eye"
          pos: [0, 0]
          quality: "rare"
        - name: "Chaos Mark"
          pos: [1, 0]
          quality: "rare"
    - name: "Shared Tab 5"
      item_count: 1
      items:
        - name: "Konnan's Maul"
          pos: [0, 0]
          quality: "unique"
    - name: "Gems"
      item_count: 0
    - name: "Materials"
      item_count: 0
    - name: "Runes"
      item_count: 0
```
