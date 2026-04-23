# TC21 - Edge Cases: Encode 2/3, Ethereal, Personalized, Weapons

## Summary

Maximum edge-case test covering previously untested code paths:
encode type 2 (chance-to-cast), encode type 3 (charges), ethereal flag,
personalized items, socketed weapons, and multiple weapon damage values.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify encode 2/3, ethereal, personalized, weapon damage fields.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0              C1              C2         C3         C4              C5
R0 [Staff]         [War Javelin]   [Thunder Maul]        [War Sword]     [Bastard Sword]
R1 [Staff]         [War Javelin]   [Thunder Maul]        [War Sword]     [Bastard Sword]
R2 [Staff]         [War Javelin]   [Thunder Maul]        [War Sword]     [Bastard Sword]
R3                                                       .               [Bastard Sword]
```

Items: 5 total (all weapons, all extended)

## Item Details

### Item 1: Staff of Shadows - Position (0,0), Size 1x3, Unique
- **Base:** Io Staff [X] (Exceptional)
- **Quality:** Unique
- **Item Level:** 67
- **Two-Hand Damage:** 6 to 21
- **Durability:** 184 / 250
- **Required Strength:** 25
- **Required Level:** 36
- **Properties:**
  - 20% Chance to Cast Level 5 Dim Vision When Struck <- **ENCODE TYPE 2**
  - +1 to All Skills
  - +20% Faster Cast Rate
  - +3 to Fire Mastery (Sorceress Only)
  - +3 to Fire Wall (Sorceress Only)
  - +3 to Blaze (Sorceress Only)
  - Physical Damage Reduced by 8
  - +50% Damage to Undead

### Item 2: Rhyme of the Bard - Position (1,0), Size 1x3, Unique
- **Base:** War Javelin [X] (Exceptional)
- **Quality:** Unique
- **Item Level:** 99
- **Throw Damage:** 43 to 99
- **One-Hand Damage:** 18 to 59
- **Quantity:** 410 / 410
- **Required Dexterity:** 25
- **Required Strength:** 25
- **Required Level:** 37
- **Properties:**
  - +35% Increased Attack Speed
  - +212% Enhanced Weapon Damage
  - Increased Stack Size
  - Replenishes Quantity
  - Level 2 War Cry (200/200 Charges) <- **ENCODE TYPE 3**
  - Level 3 Battle Orders (200/200 Charges) <- **ENCODE TYPE 3**
  - Level 3 Shout (200/200 Charges) <- **ENCODE TYPE 3**

### Item 3: Thunder Maul - Position (2,0), Size 2x3, **ETHEREAL**
- **Quality:** Normal (Superior?)
- **Item Level:** 96
- **Two-Hand Damage:** 49 to 270
- **Durability:** 126 / 126
- **Required Strength:** 243
- **Required Level:** 65
- **Properties:**
  - +50% Damage to Undead
  - Ethereal (Cannot be Repaired)
  - Socketed (4), all 4 sockets EMPTY

### Item 4: Laktana's War Sword of Blight - Position (4,0), Size 1x3, **PERSONALIZED**
- **Quality:** Magic
- **Item Level:** 45
- **One-Hand Damage:** 8 to 20
- **Durability:** 250 / 250
- **Required Dexterity:** 45
- **Required Strength:** 71
- **Required Level:** 3
- **Personalized By:** "Laktana"
- **Properties:**
  - +7 Weapon Poison Damage over 3 Seconds

### Item 5: Bastard Sword of Fire - Position (5,0), Size 1x4
- **Quality:** Magic
- **Item Level:** 45
- **Two-Hand Damage:** 20 to 28
- **Durability:** 250 / 250
- **Required Strength:** 62
- **Required Level:** 11
- **Properties:**
  - Adds 1-11 Weapon Fire Damage


## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    - name: "Staff of Shadows"
      pos: [0, 0]
      quality: "unique"
      item_level: 67
      durability_max: 250
      durability_current: 184
      properties:
        - "20% Chance to Cast Level 5 Dim Vision When Struck"
        - "+1 to All Skills"
        - "+20% Faster Cast Rate"
        - "+3 to Fire Mastery (Sorceress Only)"
        - "+3 to Fire Wall (Sorceress Only)"
        - "+3 to Blaze (Sorceress Only)"
        - "Physical Damage Reduced by 8"
        - "+50% Damage to Undead"
    - name: "Rhyme of the Bard"
      pos: [1, 0]
      quality: "unique"
      item_level: 99
      quantity: 410
      properties:
        - "+35% Increased Attack Speed"
        - "+212% Enhanced Weapon Damage"
        - "Increased Stack Size"
        - "Replenishes Quantity"
        - "Level 2 War Cry (200/200 Charges)"
        - "Level 3 Battle Orders (200/200 Charges)"
        - "Level 3 Shout (200/200 Charges)"
    - name: "Thunder Maul"
      pos: [2, 0]
      quality: "normal"
      item_level: 96
      durability_max: 126
      durability_current: 126
      ethereal: true
      sockets: 4
      sockets_filled: 0
      properties:
        - "+50% Damage to Undead"
    - name: "Laktana's War Sword of Blight"
      pos: [4, 0]
      quality: "magic"
      item_level: 45
      durability_max: 250
      durability_current: 250
      personalized_name: "Laktana"
      properties:
        - "+7 Weapon Poison Damage over 3 Seconds"
    - name: "Bastard Sword of Fire"
      pos: [5, 0]
      quality: "magic"
      item_level: 45
      durability_max: 250
      durability_current: 250
      properties:
        - "Adds 1-11 Weapon Fire Damage"
```

