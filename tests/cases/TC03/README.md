# TC03 - Full Equipment & Socketed Item

## Summary
This scenario describes a Level 12 Warlock character with a full set of equipped items. It serves as a complex test case for full equipment slot validation, personal stash parsing (expanded 16x13 grid), and specifically for items with filled sockets (Parent-Child relationship).

- **File:** TestWarlock.d2s
- **Character:** Warlock (New Class), Level 12
- **Mod Version:** D2R Reimagined v3.0.4
- **Goal:** Validate all 10 active equipment slots, the expanded personal stash, and the correct parsing of a socketed item containing a magic jewel.

## Character Profile (In-Game View)

### Statistics
Values based on the Character Screen ("C"):

- **Name:** TestWarlock
- **Class:** Warlock
- **Level:** 12
- **Experience:** 90,180
- **Gold (Inventory):** 67,655
- **Gold (Stash):** 14,545

**Attributes:**
- **Strength:** 15
- **Dexterity:** 20
- **Vitality:** 25
- **Energy:** 20
- **Stat Points Remaining:** 55

**Vitals:**
- **Life:** (Based on Vit/Class)
- **Mana:** (Based on Ene/Class)
- **Stamina:** (Base)

### Skills & Quests
- **Invested Skill Points:** 0
- **Skill Points Remaining:** 11
- **Quests:** None started (Fresh character)

## Grids & Equipment (Visuals)

### Equipped Items (Slots 1-10)
- **Head:** Skull Cap of the Efreeti
- **Amulet:** Eye of Kahn (Unique)
- **Torso:** Strong Quilted Armor of the Yeti
- **Right Hand (Primary):** Spiked Club of Maiming
- **Left Hand (Primary):** Buckler of the Elements
- **Right Ring:** Ring of Engagement (Unique)
- **Left Ring:** Lizard's Ring of Strength
- **Belt:** Light Belt of Remedy
- **Boots:** Sturdy Boots of Self-Repair
- **Gloves:** Paradox Leather Gloves of Thawing
- **Weapon Switch:** Empty

### Inventory Grid (10x8)
Coordinates are 0-based: (0,0) top-left.

   C0    C1    C2    C3    C4    C5    C6    C7    C8    C9

R0   [SL ] [SL ]  .     .     .     .     .     .     .    [OcI]
R1   [SL ] [SL ]  .     .     .     .     .     .     .     .
R2   [SL ] [SL ]  .     .     .     .     .     .     .     .
R3-6  .     .     .     .     .     .     .     .     .     .
R7   [Dia]  .     .     .     .     .     .     .     .    [OsI]

- **[SL]**: Superior Studded Leather (Socketed) - Anchor: (0,0)
- **[OcI]**: Orb of Conversion - Anchor: (9,0)
- **[Dia]**: Diamond - Anchor: (0,7)
- **[OsI]**: Orb of Socketing - Anchor: (9,7)

### Personal Stash Grid (16x13)
Coordinates are 0-based: (0,0) top-left.

   C0    ...   C4    C5    C6    ...   C12   ...   C15

R0   [Sku]  .     .     .     .     .     .     .    [OcS]
R1    .     .    [RPl]  .    [OAs]  .     .     .     .
R2    .     .     .    [GCl]  .     .     .     .     .
R3    .     .    [OIn]  .    [JPl]  .     .     .     .
R4-8  .     .     .     .     .     .     .     .     .
R9    .     .     .     .     .     .    [ORe]  .     .
R10-11.     .     .     .     .     .     .     .     .
R12  [OSh]  .     .     .     .     .     .     .    [OCo]

- **[Sku]**: Skull (0,0) | **[OcS]**: Orb of Conversion (15,0)
- **[RPl]**: Rune Pliers (4,1) | **[OAs]**: Orb of Assemblage (6,1)
- **[GCl]**: Gem Cluster (5,2) | **[OIn]**: Orb of Infusion (4,3)
- **[JPl]**: Jewel Pliers (6,3) | **[ORe]**: Orb of Renewal (12,9)
- **[OSh]**: Orb of Shadows (0,12) | **[OCo]**: Orb of Corruption (15,12)

## Item Details

### Socketed Item: Superior Studded Leather
- **Position:** Inventory (0,0)
- **Sockets:** 1 Total / 1 Filled
- **Contents:** Magic Jewel (+10 to Attack Rating, +1 to Light Radius)
- **Properties:** Includes base superior bonuses (+10% Durability).

### Unique Items
- **Eye of Kahn (Amulet):** +3 Max Damage, +9 Str, +6 Dex, +33 Life, +35 Mana.
- **Ring of Engagement (Ring):** Lvl 1 Might Aura, +2 Max Damage, +5 Str, +17 Life.

### Reimagined Utility Orbs
- Various Orbs (Conversion, Socketing, Infusion, etc.) are placed in Inventory and Stash to verify parsing of new mod-item types.

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestWarlock"
    class: "Warlock"
    level: 12
    gold_inv: 67655
    gold_stash: 14545
    unused_stats: 55
    unused_skills: 11
  equipment_count: 10
  inventory_items:
    - name: "Superior Studded Leather"
      pos: [0, 0]
      quality: "superior"
      sockets_filled: 1
      socket_contents:
        - name: "Jewel"
          quality: "magic"
          stats: ["+10 to Attack Rating", "+1 to Light Radius"]
    - name: "Orb of Conversion"
      pos: [9, 0]
    - name: "Diamond"
      pos: [0, 7]
    - name: "Orb of Socketing"
      pos: [9, 7]
  stash_items_count: 10
  stash_grid_size: [16, 13]
  belt_items: []

