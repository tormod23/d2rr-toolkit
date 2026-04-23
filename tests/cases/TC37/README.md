# TC37 - Full Set with Reimagined Modifications (Sigon's Complete Steel) (.d2s)

## Summary

This scenario extends TC36 by applying four types of **D2R Reimagined** item modifications to
the same Sigon's Complete Steel set. All six pieces remain equipped on the character body. The
goal is to verify correct parsing of:

1. **Ethereal** - Sigon's Visor (ghm) made ethereal via Orb of Shadows
2. **Socketed** - Sigon's Shelter (gth) socketed with 4 empty sockets
3. **Enchanted *3** - Sigon's Sabot (hbt) enchanted three times via Orb of Transformation
4. **Corrupted WITH extra properties** - Sigon's Gage (hgl) corrupted (gained bonus stats)
5. **Corrupted WITHOUT extra properties** - Sigon's Guard (tow) corrupted (no bonus stats)
6. **Unchanged reference** - Sigon's Wrap (hbl) left unmodified as baseline

- **File:** TestABC.d2s
- **Mod:** D2R Reimagined
- **Character:** TestABC (Barbarian, Level 42)
- **Goal:** Verify all four Reimagined modification types parse correctly on Set items.

### Key Verifications

- Item count = exactly 6 (no garbage items)
- Sigon's Visor: ethereal, defense raised from 35 to 52 (base x 1.5)
- Sigon's Shelter: 4 empty sockets
- Sigon's Sabot: 10 properties total (3 enchants applied, effects merged into existing stats)
- Sigon's Gage: corrupted with extra properties (Crushing Blow, Deadly Strike)
- Sigon's Guard: corrupted without extra properties
- Sigon's Wrap: unchanged reference matching TC36 values

### Notes on Reimagined Modifications

**Ethereal:** Reimagined does NOT display the word "Ethereal" in the item tooltip -
the modification is only visible as higher defense. Defense = floor(base x 1.5).

**Socketed:** Gloves cannot receive sockets in D2R - the Shelter (Gothic Plate) was
socketed instead.

**Enchantment:** Each application of an Orb of Transformation adds one enchant.
Enchant effects merge directly with existing stats (e.g. Cold Resist 40 to 42 after
+2 enchant). New stats are added for effects not previously present.

**Corruption:** Two outcomes observed:
- Gauntlets: corruption granted extra properties (+Strength, +AR, Crushing Blow, Deadly Strike)
- Tower Shield: corruption granted no extra properties

## Character Overview

- **Name:** TestABC
- **Class:** Barbarian
- **Level:** 42
- **Gold (Inventory):** 0

## Equipped Items (All at Body)

| Slot      | Item Name          | Item Code | Base Type        | iLvl | Modification              |
|-----------|--------------------|-----------|------------------|------|---------------------------|
| Head (1)  | Sigon's Visor      | `ghm`     | Great Helm [N]   | 99   | Ethereal                  |
| Torso (3) | Sigon's Shelter    | `gth`     | Gothic Plate [N] | 99   | Socketed (4 sockets)      |
| Shield(5) | Sigon's Guard      | `tow`     | Tower Shield [N] | 99   | Corrupted (no extra props)|
| Belt (8)  | Sigon's Wrap       | `hbl`     | Plated Belt [N]  | 99   | Unchanged (reference)     |
| Boots (9) | Sigon's Sabot      | `hbt`     | Greaves [N]      | 99   | 3* Enchanted              |
| Gloves(10)| Sigon's Gage       | `hgl`     | Gauntlets [N]    | 99   | Corrupted (extra props)   |

## Item Details

### Sigon's Visor - Great Helm [N], Slot: Head - ETHEREAL

- **Defense:** 52 (ethereal *1.5 of base 35; floor(35 * 1.5) = 52)
- **Note:** No "Ethereal" text in Reimagined tooltip; modification only visible as higher defense
- **Properties (base + 2-item bonus, unchanged):**
  - +30 to Mana
  - +25 Defense
  - +8 to Attack Rating (Per Character Level) *(2-item bonus)*

### Sigon's Shelter - Gothic Plate [N], Slot: Torso - SOCKETED (4 sockets, empty)

- **Defense:** 136 (unchanged)
- **Sockets:** 4 (empty - no gems/runes inserted)
- **Properties (base + 2-item bonus, unchanged):**
  - +25% Enhanced Defense
  - +30% Lightning Resistance
  - Attacker Takes Damage of 20 *(2-item bonus)*

### Sigon's Guard - Tower Shield [N], Slot: Shield - CORRUPTED (no extra properties)

- **Defense:** 23 (unchanged)
- **Chance to Block:** 24%
- **Corruption outcome:** No additional properties granted
- **Properties (base + corruption markers):**
  - 20% Increased Chance of Blocking
  - +1 to All Skills
  - *(Reimagined internal: Hidden Charm Passive, not shown in tooltip)*
  - *(Corruption marker: item_corrupted = 2)*
  - *(Corruption marker: item_corruptedDummy = 141 - encodes corruption outcome)*

### Sigon's Wrap - Plated Belt [N], Slot: Belt - UNCHANGED (reference)

- **Defense:** 10 (in-game shows higher with active set bonuses)
- **Properties (base + 2-item bonus, unchanged):**
  - +20 to Life
  - +20% Fire Resistance
  - +2 Defense (Per Character Level) *(2-item bonus)*

### Sigon's Sabot - Greaves [N], Slot: Boots - 3* ENCHANTED

- **Defense:** 13 (unchanged)
- **Enchants applied:** 3 (tracked via internal stat `upgrade_medium`=3)
- **Properties (base + enchant effects + 2-item + 3-item bonuses, 10 total):**
  - +25% Faster Run/Walk Speed *(was 20%, enchant added +5%)*
  - +15 to Mana *(enchant)*
  - +2 Mana After Each Kill *(enchant)*
  - +2 to Fire Resistance *(enchant: +2 All Resistances)*
  - +42% Cold Resistance *(was 40%, enchant added +2)*
  - +2% Lightning Resistance *(enchant: +2 All Resistances)*
  - +2% Poison Resistance *(enchant: +2 All Resistances)*
  - +50 to Attack Rating *(2-item bonus, unchanged)*
  - +50% Chance Items Roll Magic or Better *(3-item bonus, unchanged)*
  - *(Reimagined internal: upgrade_medium=3 tracks enchant count - not shown in tooltip)*

### Sigon's Gage - Gauntlets [N], Slot: Gloves - CORRUPTED (extra properties gained)

- **Defense:** 14 (unchanged)
- **Corruption outcome:** Extra properties granted by corruption
- **Properties (base + corruption extra props + corruption markers + 2-item bonus):**
  - +10 to Strength
  - +20 to Attack Rating
  - **+5% Chance of Crushing Blow** *(extra from corruption)*
  - **+5% Deadly Strike** *(extra from corruption)*
  - *(Corruption marker: item_corrupted = 2)*
  - *(Corruption marker: item_corruptedDummy = 180 - encodes corruption outcome)*
  - +30% Increased Attack Speed *(2-item bonus)*

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2s_character"
  mod: "D2R Reimagined"
  character:
    name: "TestABC"
    class: "Barbarian"
    level: 42
    gold: 0

  items:
    - name: "Sigon's Visor"
      base_type: "Great Helm [N]"
      item_code: "ghm"
      location: "equipped"
      equipped_slot: 1
      quality: "set"
      item_level: 99
      ethereal: true
      defense_display: 52           # floor(35 * 1.5) = 52 [BINARY_VERIFIED TC37]
      modification: "ethereal"
      properties:
        - {stat_id: 9,   value: 30, name: "maxmana"}
        - {stat_id: 31,  value: 25, name: "armorclass"}
        - {stat_id: 224, value: 16, name: "item_tohit_perlevel"}
      property_count: 3             # Unchanged from TC36

    - name: "Sigon's Shelter"
      base_type: "Gothic Plate [N]"
      item_code: "gth"
      location: "equipped"
      equipped_slot: 3
      quality: "set"
      item_level: 99
      socketed: true
      defense_display: 136
      modification: "socketed (4 empty sockets)"
      sock_unk_bits: 4              # REGRESSION: q=5 Set armor uses 4-bit sock_unk (not 20)
      sock_unk_value: 4             # = socket count [BINARY_VERIFIED TC37]
      properties:
        - {stat_id: 16,  value: 25, name: "item_armor_percent"}
        - {stat_id: 41,  value: 30, name: "lightresist"}
        - {stat_id: 78,  value: 20, name: "item_attackertakesdamage"}
      property_count: 3             # Unchanged from TC36

    - name: "Sigon's Guard"
      base_type: "Tower Shield [N]"
      item_code: "tow"
      location: "equipped"
      equipped_slot: 5
      quality: "set"
      item_level: 99
      defense_display: 23
      modification: "corrupted (no extra properties)"
      property_count: 5             # 3 base + 2 corruption markers
      properties:
        - {stat_id: 20,  value: 20,  name: "toblock"}
        - {stat_id: 97,  value: 1,   param: 449, name: "item_nonclassskill"}
        - {stat_id: 127, value: 1,   name: "item_allskills"}
        - {stat_id: 361, value: 2,   name: "item_corrupted"}       # corruption marker
        - {stat_id: 362, value: 141, name: "item_corruptedDummy"}  # outcome=141: no bonus

    - name: "Sigon's Wrap"
      base_type: "Plated Belt [N]"
      item_code: "hbl"
      location: "equipped"
      equipped_slot: 8
      quality: "set"
      item_level: 99
      defense_display: 10
      modification: "none (unchanged reference)"
      properties:
        - {stat_id: 7,   value: 20, name: "maxhp"}
        - {stat_id: 39,  value: 20, name: "fireresist"}
        - {stat_id: 214, value: 16, name: "item_armor_perlevel"}
      property_count: 3

    - name: "Sigon's Sabot"
      base_type: "Greaves [N]"
      item_code: "hbt"
      location: "equipped"
      equipped_slot: 9
      quality: "set"
      item_level: 99
      defense_display: 13
      modification: "3x enchanted"
      property_count: 10
      properties:
        # Enchantment capacity marker (Reimagined internal, not shown in tooltip)
        - {stat_id: 393, value: 3,  name: "upgrade_medium"}   # 3 enchants applied
        # Enchant-modified base stats:
        - {stat_id: 43,  value: 42, name: "coldresist"}        # was 40, +2 enchant
        - {stat_id: 96,  value: 25, name: "item_fastermovevelocity"} # was 20, +5 enchant
        # Enchant-added new stats:
        - {stat_id: 39,  value: 2,  name: "fireresist"}        # new from enchant
        - {stat_id: 41,  value: 2,  name: "lightresist"}       # new from enchant
        - {stat_id: 45,  value: 2,  name: "poisonresist"}      # new from enchant
        - {stat_id: 9,   value: 15, name: "maxmana"}           # new from enchant
        - {stat_id: 138, value: 2,  name: "item_manaafterkill"} # new from enchant
        # Set bonus list properties (unchanged):
        - {stat_id: 19,  value: 50, name: "tohit"}             # 2-item bonus
        - {stat_id: 80,  value: 50, name: "item_magicbonus"}   # 3-item bonus

    - name: "Sigon's Gage"
      base_type: "Gauntlets [N]"
      item_code: "hgl"
      location: "equipped"
      equipped_slot: 10
      quality: "set"
      item_level: 99
      defense_display: 14
      modification: "corrupted (extra properties gained)"
      property_count: 7
      properties:
        # Base properties:
        - {stat_id: 0,   value: 10,  name: "strength"}
        - {stat_id: 19,  value: 20,  name: "tohit"}
        # Extra properties from corruption:
        - {stat_id: 136, value: 5,   name: "item_crushingblow"}   # [BV TC37]
        - {stat_id: 141, value: 5,   name: "item_deadlystrike"}   # [BV TC37]
        # Corruption markers:
        - {stat_id: 361, value: 2,   name: "item_corrupted"}       # always val=2
        - {stat_id: 362, value: 180, name: "item_corruptedDummy"}  # outcome=180: bonus stats
        # 2-item set bonus:
        - {stat_id: 93,  value: 30,  name: "item_fasterattackrate"}
```

