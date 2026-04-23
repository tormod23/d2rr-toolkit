# TC01 - Basic Barbarian

## Summary
This scenario describes a minimal test character to validate basic character data and simple items. It features a Level 42 Barbarian with no points invested into attributes or skills. The items in the belt are original starter equipment.

- **File:** TestABC.d2s
- **Character:** Barbarian, Level 42
- **Goal:** Correct extraction of base stats, gold, and simple "Superior" and "Magic" items. Specifically testing the "Starter Item" flag on belt potions.

## Character Profile (In-Game View)

### Statistics
Values based on the Character Screen ("C"):

- **Name:** TestABC
- **Class:** Barbarian
- **Level:** 42
- **Experience:** 21,376,515
- **Gold (Inventory):** 419,458
- **Gold (Stash):** 0

**Attributes:**
- **Strength:** 30
- **Dexterity:** 20
- **Vitality:** 25
- **Energy:** 10
- **Stat Points Remaining:** 205

**Vitals:**
- **Life:** 137 / 137
- **Mana:** 51 / 51
- **Stamina:** 133 / 133

### Skills
- **Invested Points:** 0
- **Skill Points Remaining:** 41

## Inventory & Equipment (Visuals)

### Equipped Items
All equipment slots (Head, Torso, Weapon Slots, Rings etc.) are empty.

### Inventory Grid (10x8)
Coordinates are 0-based: (0,0) top-left to (9,7) bottom-right.

   C0    C1    C2    C3    C4    C5    C6    C7    C8    C9

R0   [SSd] [Spr] [Spr]  .     .     .     .     .     .     .
R1   [SSd] [Spr] [Spr]  .     .     .     .     .     .     .
R2   [SSd] [Spr] [Spr]  .     .     .     .     .     .     .
R3    .    [Spr] [Spr]  .     .     .     .     .     .     .
R4-7  .     .     .     .     .     .     .     .     .     .

- **[SSd]**: Superior Short Sword - Anchor: (0,0)
- **[Spr]**: Vicious Spear - Anchor: (1,0)

### Belt Grid (4x1)
No belt equipped (base slots only). All potions are starter items.
- **Slot 0 - 3:** 1x Minor Healing Potion each (Starter Items)

## Item Details

### Item 1: Superior Short Sword
- **Quality:** Superior
- **Position:** Inventory (0,0)
- **Size:** 1x3
- **Properties:**
  - +1 to Maximum Weapon Damage
  - +1 to Attack Rating
  - Durability: 250 of 250
  - Starter Item: No

### Item 2: Vicious Spear
- **Quality:** Magic
- **Position:** Inventory (1,0)
- **Size:** 2x4
- **Properties:**
  - +31% Enhanced Weapon Damage
  - Durability: 250 of 250
  - Starter Item: No

### Items 3-6: Minor Healing Potions
- **Quality:** Normal
- **Position:** Belt Slots 0, 1, 2, 3
- **Starter Item:** Yes (default character creation potions)

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestABC"
    class: "Barbarian"
    level: 42
    gold_inv: 419458
    unused_stats: 205
    unused_skills: 41
  inventory_items:
    - name: "Superior Short Sword"
      pos: [0, 0]
      quality: "superior"
      is_starter: false
      stats: ["+1 to Maximum Weapon Damage", "+1 to Attack Rating"]
    - name: "Vicious Spear"
      pos: [1, 0]
      quality: "magic"
      is_starter: false
      stats: ["+31% Enhanced Weapon Damage"]
  belt_items:
    - name: "Minor Healing Potion"
      count: 4
      slots: [0, 1, 2, 3]
      is_starter: true
  storage_empty:
    - "personal_stash"
    - "equipped_slots"
    - "mercenary"

