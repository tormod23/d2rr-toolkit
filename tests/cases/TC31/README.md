# TC31 - Shared Stash - Isolated Problem Items

## Summary

This scenario isolates three complex items from TC06 that caused parse failures. Each item is placed alone in its own tab, enabling targeted debugging without interference from other items. The items feature Reimagined-specific stats, custom graphics, ethereal+indestructible combinations, and set quality armor.

- **File:** ModernSharedStashSoftCoreV2.d2i
- **Mod:** D2R Reimagined
- **Goal:** Provide isolated test targets for a Unique ring, a Unique socketed shield with custom graphics, and a Set ethereal indestructible armor.

## Stash Overview

Items are present in Tabs 1, 2, and 3. Tabs 4 and 5 are empty. The Gems, Materials, and Runes tabs are empty. Gold: 0.

Grid dimensions per tab: 16 columns x 13 rows.

## Tab Contents

### Shared Tab 1
- **The Stone Of Jordan** - Position: (0,0)

### Shared Tab 2
- **Spike Thorn** - Position: (0,0)

### Shared Tab 3
- **Darkmage's Falling Star** - Position: (0,0)

### Shared Tabs 4-5 / Gems / Materials / Runes
- *(all empty)*

## Item Details

### Shared Tab 1

1. **The Stone Of Jordan**
   - **Base Type:** Ring
   - **Quality:** Unique
   - **Item Level:** 99
   - **Required Level:** 29
   - **Properties:**
     - +1 To All Skills
     - Adds 25-50 Weapon Lightning Damage
     - +20 To Mana
     - +25% Increased Maximum Mana

### Shared Tab 2

1. **Spike Thorn**
   - **Base Type:** Blade Barrier [E]
   - **Quality:** Unique
   - **Item Level:** 99
   - **Custom Graphics:** Yes (visible unique appearance)
   - **Defense:** 410
   - **Chance To Block:** 45%
   - **Durability:** 41 Of 83
   - **Required Strength:** 118
   - **Required Level:** 80
   - **Sockets:** 3 (empty)
   - **Properties:**
     - Level 29 Thorns Aura When Equipped
     - +30% Faster Hit Recovery
     - +150% Enhanced Defense
     - +17% Physical Damage Reduction
     - Attacker Takes Damage Of 294 (Based On Character Level)

### Shared Tab 3

1. **Darkmage's Falling Star**
   - **Base Type:** Boneweave [E]
   - **Quality:** Set
   - **Item Level:** 99
   - **Defense:** 2034
   - **Required Strength:** 148
   - **Required Level:** 73
   - **Ethereal:** Yes (Cannot Be Repaired)
   - **Indestructible:** Yes
   - **Sockets:** 1 (empty)
   - **Properties:**
     - +168% Enhanced Defense

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2i_shared_stash"
  mod: "D2R Reimagined"
  grid_dimensions: [16, 13]

  tabs:
    - name: "Shared Tab 1"
      item_count: 1
      items:
        - name: "The Stone Of Jordan"
          pos: [0, 0]
          quality: "unique"
          item_level: 99
          required_level: 29
          properties:
            - "+1 To All Skills"
            - "Adds 25-50 Weapon Lightning Damage"
            - "+20 To Mana"
            - "+25% Increased Maximum Mana"
    - name: "Shared Tab 2"
      item_count: 1
      items:
        - name: "Spike Thorn"
          base_type: "Blade Barrier [E]"
          pos: [0, 0]
          quality: "unique"
          item_level: 99
          custom_graphics: true
          defense: 410
          chance_to_block: 45
          durability_current: 41
          durability_max: 83
          required_strength: 118
          required_level: 80
          sockets: 3
          socket_contents: []
          properties:
            - "Level 29 Thorns Aura When Equipped"
            - "+30% Faster Hit Recovery"
            - "+150% Enhanced Defense"
            - "+17% Physical Damage Reduction"
            - "Attacker Takes Damage Of 294"
    - name: "Shared Tab 3"
      item_count: 1
      items:
        - name: "Darkmage's Falling Star"
          base_type: "Boneweave [E]"
          pos: [0, 0]
          quality: "set"
          item_level: 99
          defense: 2034
          required_strength: 148
          required_level: 73
          is_ethereal: true
          is_indestructible: true
          sockets: 1
          socket_contents: []
          properties:
            - "+168% Enhanced Defense"
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
  total_items: 3
```

