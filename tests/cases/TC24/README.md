# TC24 - Socketed Items, Runewords, Child Items (Jewels)

## Summary

Tests the most complex item structures in D2: **socketed items with child items**.
Three socketed items with increasing complexity:

1. **Runeword "Glory"** - 4-socket Boneweave [E] with 4x Ist runes
2. **Runeword "Revenge"** - 2-socket Light Plate [N] with Thul+Eld runes (same as TC22)
3. **Gemmed Thresher [E]** - 4-socket weapon with 4 different Jewels (Magic, Rare, Magic, Unique)

Key test targets:
- **Socket child item parsing** - child items stored inside parent sockets
- **Child item property aggregation** - parent displays sum of all child properties
- **Runeword properties** - runeword-specific bonus properties
- **Mixed quality child items** - Magic, Rare, Unique jewels in same socket group
- **Ethereal weapon with sockets** - tests ethereal + socketed combination

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify socket child parsing, runeword structure, property aggregation.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold / Stats / Skills:** none

## Inventory Layout (10x8)

```
   C0       C1       C2       C3       C4       C5
R0 [Glory]  [Glory]  [Revng]  [Revng]  [Thresh] [Thresh]
R1 [Glory]  [Glory]  [Revng]  [Revng]  [Thresh] [Thresh]
R2 [Glory]  [Glory]  [Revng]  [Revng]  [Thresh] [Thresh]
R3 .        .        .        .        [Thresh] [Thresh]
```

Visible items: 3 (parent items in inventory)
Total items in file: 3 parents + 4 runes (Glory) + 2 runes (Revenge) + 4 jewels (Thresher) = **13 items**

## Item Details

### === ITEM 1: Runeword "Glory" - Position (0,0), Size 2x3 ===

- **Base:** Boneweave [E] (Elite Armor)
- **Quality:** Normal (Runeword)
- **Runeword:** Glory
- **Runes:** Ist + Ist + Ist + Ist (4 sockets, all filled)
- **Item Level:** 99
- **Ethereal:** No (Boneweave is regular)
- **Defense:** 1037
- **Durability:** 34 / 45
- **Required Strength:** 111
- **Required Level:** 51
- **Runeword Properties:**
  - +2 to All Skills
  - +35% Faster Cast Rate
  - +25% Faster Hit Recovery
  - +105% Enhanced Defense
  - +25% Increased Maximum Life
  - +25% Increased Maximum Mana
  - +100% Chance Items Roll Magic or Better
  - Requirements Reduced By -30%
  - Socketed (4)

#### Child Items (4x Ist Rune):
Each Ist rune is socketed inside the parent armor.

### === ITEM 2: Runeword "Revenge" - Position (2,0), Size 2x3 ===

- **Base:** Light Plate [N] (Normal Armor)
- **Quality:** Normal (Runeword)
- **Runeword:** Revenge
- **Runes:** Thul + Eld (2 sockets, both filled)
- **Item Level:** 99
- **Defense:** 92
- **Durability:** 56 / 60
- **Required Strength:** 41
- **Required Level:** 26
- **Runeword Properties:**
  - +1 to Sorceress Skill Levels
  - +15% Faster Cast Rate
  - +65 to Mana
  - +69% Mana Regeneration
  - +6% Magic Resistance
  - +30% Cold Resistance
  - +5 Life After Each Kill
  - +3% to Experience Gained
  - +3 to Required Level
  - Socketed (2)

#### Child Items:
- Thul rune (socketed)
- Eld rune (socketed)

**Note:** Same runeword as TC22. Cross-reference for consistency.

### === ITEM 3: Gemmed Thresher [E] - Position (4,0), Size 2x4 ===

- **Base:** Thresher [E] (Elite Polearm)
- **Quality:** Normal
- **Item Level:** 92
- **Ethereal:** Yes
- **Two-Hand Damage:** 12 to 141 (base, before jewel mods)
- **Durability:** 189 / 250
- **Required Dexterity:** 118
- **Required Strength:** 152
- **Required Level:** 53 (base, increased to 67 by jewel requirements)
- **Sockets:** 4 (all filled with Jewels)
- **Combined Display Properties (base + all 4 jewels):**
  - +10% Faster Cast Rate (from Diamond Facet)
  - 6% Increased Chance of Blocking (from Diamond Facet)
  - +8 to Minimum Weapon Damage (from Rune Eye)
  - +4 to Maximum Weapon Damage (from Rune Eye)
  - +10 to Attack Rating (from Bright Jewel of Spirit)
  - +6 to Energy (from Rune Eye)
  - +19 to Life (from Jewel of Hope 13 + Bright Jewel 6)
  - +24% to All Resistances (from Rune Eye 15% + Diamond Facet 9%)
  - +4% Physical Damage Reduction (from Diamond Facet)
  - +1 to Light Radius (from Bright Jewel of Spirit)
  - Two-Hand Damage: 20-145 (base 12-141 + 8 min + 4 max)

#### Child Item 1: Jewel of Hope - Magic Quality
- **Code:** jwl
- **Quality:** Magic
- **Item Level:** 99
- **Required Level:** 37
- **Properties:**
  - +13 to Life

#### Child Item 2: Rune Eye - Rare Quality (Unique Jewel)
- **Code:** jwl
- **Quality:** Rare
- **Item Level:** 98
- **Required Level:** 37
- **Properties:**
  - +8 to Minimum Weapon Damage
  - +4 to Maximum Weapon Damage
  - +6 to Energy
  - +15% to All Resistances

#### Child Item 3: Bright Jewel of Spirit - Magic Quality
- **Code:** jwl
- **Quality:** Magic
- **Item Level:** 1
- **Required Level:** (none shown, from mods)
- **Properties:**
  - +10 to Attack Rating
  - +6 to Life
  - +1 to Light Radius
- **Note:** iLvl=1 is unusual - may indicate a crafted/gambled jewel

#### Child Item 4: Diamond Facet - Unique Quality
- **Code:** jwl
- **Quality:** Unique
- **Item Level:** 99
- **Required Level:** 67
- **Properties:**
  - +10% Faster Cast Rate
  - 6% Increased Chance of Blocking
  - +9% to All Resistances
  - +4% Physical Damage Reduction
- **Note:** The highest reqLvl (67) from the Diamond Facet becomes the Thresher's displayed reqLvl.


## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    # Parent Item 1: Runeword Glory
    - name: "Glory"
      base: "Boneweave"
      code: "bnw"
      pos: [0, 0]
      quality: "normal"
      runeword: true
      item_level: 99
      defense: 1037
      durability_max: 45
      durability_current: 34
      sockets: 4
      sockets_filled: 4
      child_items:
        - code: "r24"  # Ist rune (verify code)
          simple: true
        - code: "r24"
          simple: true
        - code: "r24"
          simple: true
        - code: "r24"
          simple: true
      runeword_properties:
        - "+2 to All Skills"
        - "+35% Faster Cast Rate"
        - "+25% Faster Hit Recovery"
        - "+105% Enhanced Defense"
        - "+25% Increased Maximum Life"
        - "+25% Increased Maximum Mana"
        - "+100% Chance Items Roll Magic or Better"
        - "Requirements Reduced By -30%"

    # Parent Item 2: Runeword Revenge
    - name: "Revenge"
      base: "Light Plate"
      code: "ltp"
      pos: [2, 0]
      quality: "normal"
      runeword: true
      item_level: 99
      defense: 92
      durability_max: 60
      durability_current: 56
      sockets: 2
      sockets_filled: 2
      child_items:
        - code: "r07"  # Thul rune (verify code)
          simple: true
        - code: "r02"  # Eld rune (verify code)
          simple: true
      runeword_properties:
        - "+1 to Sorceress Skill Levels"
        - "+15% Faster Cast Rate"
        - "+65 to Mana"
        - "+69% Mana Regeneration"
        - "+6% Magic Resistance"
        - "+30% Cold Resistance"
        - "+5 Life After Each Kill"
        - "+3% to Experience Gained"
        - "+3 to Required Level"

    # Parent Item 3: Gemmed Thresher
    - name: "Thresher"
      code: "gth"  # or "7s8" - verify!
      pos: [4, 0]
      quality: "normal"
      runeword: false
      ethereal: true
      item_level: 92
      durability_max: 250
      durability_current: 189
      sockets: 4
      sockets_filled: 4
      child_items:
        - name: "Jewel of Hope"
          code: "jwl"
          quality: "magic"
          item_level: 99
          properties:
            - "+13 to Life"
        - name: "Rune Eye"
          code: "jwl"
          quality: "rare"
          item_level: 98
          properties:
            - "+8 to Minimum Weapon Damage"
            - "+4 to Maximum Weapon Damage"
            - "+6 to Energy"
            - "+15% to All Resistances"
        - name: "Bright Jewel of Spirit"
          code: "jwl"
          quality: "magic"
          item_level: 1
          properties:
            - "+10 to Attack Rating"
            - "+6 to Life"
            - "+1 to Light Radius"
        - name: "Diamond Facet"
          code: "jwl"
          quality: "unique"
          item_level: 99
          properties:
            - "+10% Faster Cast Rate"
            - "6% Increased Chance of Blocking"
            - "+9% to All Resistances"
            - "+4% Physical Damage Reduction"
  total_items_in_file: 13  # 3 parents + 4 + 2 + 4 children
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
