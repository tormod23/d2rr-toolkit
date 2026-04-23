# TC02 - Studded Leather Showcase

## Summary
This scenario validates the parsing of different item qualities using five Studded Leather armors on the same character. It also tests the presence of gold in the personal stash and the "started" state of a quest.

- **File:** TestABC.d2s
- **Character:** Barbarian, Level 42
- **Goal:** Verify parsing of all five quality levels (Normal, Magic, Rare, Unique, Set) and their respective data fields (Defense, Durability, Affixes). Also testing Quest status and Stash gold.

## Character Profile (In-Game View)

### Statistics
Values based on the Character Screen ("C"):

- **Name:** TestABC
- **Class:** Barbarian
- **Level:** 42
- **Gold (Inventory):** 415,144
- **Gold (Stash):** 4,194 (Previously 0 in TC01)

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

### Quest Log
- **Act 1:** Quest 1 (Den of Evil) has been **started** (active, but not completed).
- All other quests in all acts are uninitiated.

## Inventory & Equipment (Visuals)

### Equipped Items
All equipment slots are **empty**.

### Inventory Grid (10x8)
Coordinates are 0-based: (0,0) top-left. All items are Studded Leather (2x3).

   C0    C1    C2    C3    C4    C5    C6    C7    C8    C9

R0   [Nrm] [Nrm] [Mag] [Mag] [Rar] [Rar] [Uni] [Uni] [Set] [Set]
R1   [Nrm] [Nrm] [Mag] [Mag] [Rar] [Rar] [Uni] [Uni] [Set] [Set]
R2   [Nrm] [Nrm] [Mag] [Mag] [Rar] [Rar] [Uni] [Uni] [Set] [Set]
R3-7  .     .     .     .     .     .     .     .     .     .

- **[Nrm]**: Normal Studded Leather - Anchor: (0,0)
- **[Mag]**: Magic Studded Leather - Anchor: (2,0)
- **[Rar]**: Rare Studded Leather - Anchor: (4,0)
- **[Uni]**: Unique Studded Leather - Anchor: (6,0)
- **[Set]**: Set Studded Leather - Anchor: (8,0)

### Belt Grid (4x1)
No belt equipped.
- **Slot 0 - 3:** 1x Minor Healing Potion each (Bought from Akara, NOT starter items)

## Item Details

### Item 1: Studded Leather (Normal)
- **Quality:** Normal
- **Position:** Inventory (0,0)
- **Defense:** 32
- **Durability:** 32 of 32
- **Properties:** None

### Item 2: Coral Studded Leather of Swords (Magic)
- **Quality:** Magic
- **Position:** Inventory (2,0)
- **Defense:** 32
- **Durability:** 32 of 32
- **Properties:** - +29% Lightning Resistance
  - Attacker Takes Damage of 42

### Item 3: Scarab of Protection (Rare)
- **Quality:** Rare
- **Position:** Inventory (4,0)
- **Defense:** 144
- **Durability:** 18 of 32
- **Properties:**
  - +15% Faster Block Rate
  - +111 Defense
  - +37 to Life
  - +10% Magic Resistance
  - +20% to All Resistances
  - Physical Damage Reduced By 11

### Item 4: Blood Mantle (Unique)
- **Quality:** Unique
- **Position:** Inventory (6,0)
- **Defense:** 56
- **Durability:** 21 of 32
- **Properties:**
  - Level 3 Sanctuary Aura When Equipped
  - +56% Enhanced Defense
  - Replenish Life +4
  - +20% Magic Resistance
  - +10% Physical Damage Reduction
  - Attacker Takes Damage of 42 (Based on Character Level)

### Item 5: Jakira's Leather Jerkin (Set)
- **Quality:** Set
- **Position:** Inventory (8,0)
- **Defense:** 79
- **Durability:** 21 of 32
- **Properties:**
  - +45 Defense
  - +15 to Strength
  - +15 to Dexterity
  - Partial Set Bonus (3 Items): Physical Damage Reduced By 8

### Items 6-9: Minor Healing Potions
- **Quality:** Normal (Compact)
- **Position:** Belt Slots 0, 1, 2, 3
- **Properties:** Starter Item: No

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestABC"
    level: 42
    gold_inv: 415144
    gold_stash: 4194
    quests:
      act1_q1: "started"
  inventory_items:
    - name: "Studded Leather"
      pos: [0, 0]
      quality: "normal"
      defense: 32
    - name: "Coral Studded Leather of Swords"
      pos: [2, 0]
      quality: "magic"
      stats: ["+29% Lightning Resistance", "Attacker Takes Damage of 42"]
    - name: "Scarab of Protection"
      pos: [4, 0]
      quality: "rare"
      defense: 144
      stats: ["+15% Faster Block Rate", "+111 Defense", "+37 to Life", "+10% Magic Resistance", "+20% to All Resistances", "Physical Damage Reduced By 11"]
    - name: "Blood Mantle"
      pos: [6, 0]
      quality: "unique"
      defense: 56
      stats: ["Level 3 Sanctuary Aura When Equipped", "+56% Enhanced Defense", "Replenish Life +4", "+20% Magic Resistance", "+10% Physical Damage Reduction", "Attacker Takes Damage of 42"]
    - name: "Jakira's Leather Jerkin"
      pos: [8, 0]
      quality: "set"
      defense: 79
      stats: ["+45 Defense", "+15 to Strength", "+15 to Dexterity"]
      partial_set_bonus: {"threshold": 3, "stat": "Physical Damage Reduced By 8"}
  belt_items:
    - name: "Minor Healing Potion"
      count: 4
      slots: [0, 1, 2, 3]
      is_starter: false

