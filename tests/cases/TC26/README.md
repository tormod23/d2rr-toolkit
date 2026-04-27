# TC26 - Crafted Items

## Summary

Sorceress character with 8 Crafted items in the inventory: 3 Rings, 1 Amulet,
1 Body Armor, 1 Boots, 1 Shield, and 1 Belt. All items are Crafted quality.
This tests Crafted quality items across multiple item types.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify Crafted item parsing for rings, amulet, armor, boots, shield, and belt.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Experience:** 0
- **Gold (Inventory):** 0
- **Gold (Stash):** 0
- **All attributes:** class base, no points spent
- **Skills:** 0 invested, 0 remaining

## Items

### Equipped Items
ALL equipment slots are **empty**.

### Inventory Grid (10x4)
```
   C0         C1         C2         C3         C4    C5    C6    C7    C8    C9
R0  [Ring1]    [Ring2]    [Ring3]    [Amu]      [--- Leather Armor ---]  [---    ---]  [--- Round Shield ---]
R1  [--- Demonhide Sash ---]  ...
```

Positions:
- Order Grasp (Ring) - (0,0)
- Bone Loop (Ring) - (1,0)
- Ghoul Turn (Ring) - (2,0)
- Beast Emblem (Amulet) - (3,0)
- Eagle Jack (Leather Armor) - (4,0), 2x3
- Skull Shank (Sharkskin Boots) - (6,0), 2x2
- Brimstone Aegis (Round Shield) - (8,0), 2x2
- Havoc Lash (Demonhide Sash) - (0,1), 2x1

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Order Grasp - Crafted Ring (Inventory 0,0)
- **Quality:** Crafted
- **Required Level:** 72
- **Item Level:** 98
- **Properties:**
  - +1 to All Skills
  - Adds 15-25 Weapon Damage
  - +119 to Attack Rating
  - +3 to Holy Freeze (Paladin Only)
  - +6 Defense
  - +7% to All Resistances

### Item 2: Bone Loop - Crafted Ring (Inventory 1,0)
- **Quality:** Crafted
- **Required Level:** 97
- **Item Level:** 98
- **Properties:**
  - +1 to All Skills
  - Adds 15-35 Weapon Damage
  - +5 to Blade Sentinel (Assassin Only)
  - +15% to All Resistances
  - +8% Chance Items Roll Magic or Better

### Item 3: Ghoul Turn - Crafted Ring (Inventory 2,0)
- **Quality:** Crafted
- **Required Level:** 97
- **Item Level:** 98
- **Properties:**
  - +1 to All Skills
  - Adds 15-25 Weapon Damage
  - +5 to Lightning Sentry (Assassin Only)
  - +11% Poison Resistance
  - +3 Life after each Kill
  - +9% Chance Items Roll Magic or Better

### Item 4: Beast Emblem - Crafted Amulet (Inventory 3,0)
- **Quality:** Crafted
- **Required Level:** 53
- **Item Level:** 98
- **Properties:**
  - +2 to All Skills
  - +10% to All Elemental Skill Damage
  - +37 to Life
  - +18% to All Resistances
  - Magic Damage Reduced By 4
  - +32% Chance Items Roll Magic or Better

### Item 5: Eagle Jack - Crafted Leather Armor (Inventory 4,0)
- **Quality:** Crafted
- **Defense:** 48
- **Durability:** 14 of 24
- **Required Strength:** 15
- **Required Level:** 94
- **Item Level:** 98
- **Properties:**
  - Level 3 Conviction Aura When Equipped
  - +2 to All Skills
  - +167% Enhanced Defense
  - +86 to Life
  - +15% Magic Resistance
  - +25% to All Resistances
  - +10% Physical Damage Reduction
  - Attacker Takes Damage of 47

### Item 6: Skull Shank - Crafted Sharkskin Boots (Inventory 6,0)
- **Quality:** Crafted
- **Defense:** 77
- **Durability:** 14 of 14
- **Required Strength:** 47
- **Required Level:** 74
- **Item Level:** 98
- **Properties:**
  - +1 to All Skills
  - +28% Faster Run/Walk Speed
  - Adds 20-30 Weapon Damage
  - +93% Enhanced Defense
  - Replenish Life +5
  - +4% to Maximum Cold Resistance
  - Repairs 1 durability in 20 seconds

### Item 7: Brimstone Aegis - Crafted Round Shield (Inventory 8,0)
- **Quality:** Crafted
- **Defense:** 102
- **Chance to Block:** 32%
- **Required Strength:** 53
- **Required Level:** 70
- **Item Level:** 98
- **Properties:**
  - Indestructible
  - +2 to All Skills
  - -14% to All Enemy Elemental Resistances
  - +14% to All Elemental Skill Damage
  - +83% Enhanced Defense
  - +28% Cold Resistance
  - Half Freeze Duration

### Item 8: Havoc Lash - Crafted Demonhide Sash (Inventory 0,1)
- **Quality:** Crafted
- **Defense:** 111
- **Belt Size:** +12 Slots
- **Durability:** 11 of 12
- **Required Strength:** 20
- **Required Level:** 97
- **Item Level:** 98
- **Properties:**
  - +1 to All Skills
  - +7% to All Elemental Skill Damage
  - +2 to Poison Dagger (Necromancer Only)
  - +218% Enhanced Defense
  - +11 to Strength
  - +0% Poison Resistance (Based on Character Level)

## Notes

- The Crafted Round Shield "Brimstone Aegis" is Indestructible. In D2R Reimagined,
  Indestructible items still have non-zero max durability (unlike vanilla D2 where
  max durability would be 0).
- The three rings and the amulet use Reimagined-internal stats that the parser may
  not fully decode. The in-game displayed properties listed above are correct and
  complete.

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2s_character"
  mod: "D2R Reimagined"
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
    gold: 0

  total_items: 8

  items:
    # === Rings ===
    - name: "Order Grasp"
      item_code: "rin"
      location: "inventory"
      pos: [0, 0]
      quality: "crafted"
      item_level: 98
      properties_complete: false

    - name: "Bone Loop"
      item_code: "rin"
      location: "inventory"
      pos: [1, 0]
      quality: "crafted"
      item_level: 98
      properties_complete: false

    - name: "Ghoul Turn"
      item_code: "rin"
      location: "inventory"
      pos: [2, 0]
      quality: "crafted"
      item_level: 98
      properties_complete: false

    # === Amulet ===
    - name: "Beast Emblem"
      item_code: "amu"
      location: "inventory"
      pos: [3, 0]
      quality: "crafted"
      item_level: 98
      properties_complete: false

    # === Body Armor ===
    - name: "Eagle Jack"
      item_code: "lea"
      location: "inventory"
      pos: [4, 0]
      quality: "crafted"
      item_level: 98
      durability_current: 14
      durability_max: 24
      properties:
        - "+2 to All Skills"
        - "+167% Enhanced Defense"
        - "+86 to Life"
        - "+25% to All Resistances"
        - "+10% Physical Damage Reduction"
        - "Attacker Takes Damage of 47"
        - "Level 3 Conviction Aura When Equipped"

    # === Boots ===
    - name: "Skull Shank"
      item_code: "xvb"
      location: "inventory"
      pos: [6, 0]
      quality: "crafted"
      item_level: 98
      durability_current: 14
      durability_max: 14
      properties:
        - "+1 to All Skills"
        - "+93% Enhanced Defense"
        - "+28% Faster Run/Walk Speed"
        - "Adds 20-30 Weapon Damage"
        - "Replenish Life +5"
        - "+4% to Maximum Cold Resistance"
        - "Repairs 1 Durability in 20 Seconds"

    # === Round Shield (Indestructible) ===
    - name: "Brimstone Aegis"
      item_code: "xml"
      location: "inventory"
      pos: [8, 0]
      quality: "crafted"
      item_level: 98
      durability_current: 40
      durability_max: 64
      indestructible: true
      properties:
        - "Indestructible"
        - "+2 to All Skills"
        - "+83% Enhanced Defense"
        - "+28% Cold Resistance"
        - "Half Freeze Duration"
        - "+14% to All Elemental Skill Damage"
        - "-14% to All Enemy Elemental Resistances"

    # === Belt ===
    - name: "Havoc Lash"
      item_code: "zlb"
      location: "inventory"
      pos: [0, 1]
      quality: "crafted"
      item_level: 98
      durability_current: 11
      durability_max: 12
      properties:
        - "+1 to All Skills"
        - "+218% Enhanced Defense"
        - "+11 to Strength"
```
