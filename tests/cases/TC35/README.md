# TC35 - Encode 2 (Skill-on-Event) + Encode 3 (Charged Skills) (.d2s)

## Summary

This scenario tests skill-on-event properties ("chance to cast when struck") and charged
skill properties ("Level X Skill (Y/Y Charges)"). Three Unique items cover these cases
alongside standard stat properties with known display values.

- **File:** TestSorc.d2s
- **Mod:** D2R Reimagined
- **Character:** TestSorc (Sorceress, Level 1)
- **Goal:** Verify correct property decoding for skill-on-event and charged skill properties.

### Key Verifications
- **Skill-on-event** - "25% Chance to cast level 1 Teleport when struck" (The Oculus)
- **Charged skills** - War Cry, Battle Orders, Shout charges (Rhyme of the Bard)
- **Class skill bonuses** - "+3 to Sorceress Skill Levels"
- **Throwing weapon** - War Javelin with quantity and multiple charged skills

## Character Overview

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold (Inventory):** 0
- **Gold (Stash):** 0

## Inventory Contents

| Pos   | Item                        | Quality | Notes                                    |
|-------|-----------------------------|---------|------------------------------------------|
| (0,0) | The Oculus                  | Unique  | Swirling Crystal [X], iLvl 64            |
| (1,0) | Rhyme of the Bard           | Unique  | War Javelin [N], iLvl 99, qty 410/410    |
| (2,0) | Golem's Might               | Unique  | Ring, iLvl 99                            |

## Item Details

### The Oculus - Position: (0,0)

- **Base Type:** Swirling Crystal [X] (item code: `oba`)
- **Quality:** Unique
- **Item Level:** 64
- **One-Hand Damage:** 18 to 42
- **Durability:** 212 of 250
- **Required Level:** 42
- **Sorceress Only**
- **Properties:**
  - 25% Chance to cast level 1 Teleport when struck
  - +3 to Sorceress Skill Levels
  - +30% Faster Cast Rate
  - +20% Enhanced Defense
  - +20 to Vitality
  - +20 to Energy
  - +20% to All Resistances
  - +5 to Mana after each Kill
  - +50% Chance Items Roll Magic or Better

### Rhyme of the Bard - Position: (1,0)

- **Base Type:** War Javelin [N] (item code: `9ja`)
- **Quality:** Unique
- **Item Level:** 99
- **Throw Damage:** 43 to 99
- **One-Hand Damage:** 18 to 59
- **Quantity:** 410 of 410
- **Required Dexterity:** 25
- **Required Strength:** 25
- **Required Level:** 37
- **Properties:**
  - +35% Increased Attack Speed
  - +212% Enhanced Weapon Damage
  - Increased Stack Size
  - Replenishes quantity
  - Level 2 War Cry (200/200 Charges)
  - Level 3 Battle Orders (200/200 Charges)
  - Level 3 Shout (200/200 Charges)

### Golem's Might - Position: (2,0)

- **Base Type:** Ring (item code: `rin`)
- **Quality:** Unique
- **Item Level:** 99
- **Required Level:** 24
- **Properties:**
  - +10% Increased Attack Speed
  - Adds 10-15 Weapon Damage
  - +25 to Strength
  - +11% to All Resistances
  - +8 Life after each Kill

## Notes

### Skill ID Verification (cross-referenced against skills.txt)

| skill_id | Name              | Class     | Context                                    |
|----------|-------------------|-----------|--------------------------------------------|
| 54       | Teleport          | Sorceress | The Oculus: "25% Chance to cast level 1 Teleport when struck" |
| 138      | Shout             | Barbarian | Rhyme of the Bard: Level 3 Shout (200/200 Charges) |
| 149      | Battle Orders     | Barbarian | Rhyme of the Bard: Level 3 Battle Orders (200/200 Charges) |
| 154      | War Cry           | Barbarian | Rhyme of the Bard: Level 2 War Cry (200/200 Charges) |
| 449      | Hidden Charm Passive | (none) | Internal Reimagined modifier on Unique items - not shown in tooltip |

**Binary storage order vs. in-game display order:**
The binary stores charged skills as Shout (138) -> Battle Orders (149) -> War Cry (154).
The in-game tooltip displays them in reverse: War Cry -> Battle Orders -> Shout.
This is a display-ordering difference only; parser correctly reads all three.

### Reimagined "Adds X-Y Weapon Damage" on Rings

Golem's Might stores the damage range as three separate stat pairs in the binary:
- stats 21+22 (mindamage/maxdamage): melee weapon damage bonus
- stats 23+24 (secondary_mindamage/maxdamage): secondary attack damage bonus
- stats 159+160 (item_throw_mindamage/maxdamage): throwing weapon damage bonus

All six stats carry the same value pair (10/15). The in-game tooltip shows a single
"Adds 10-15 Weapon Damage" line. This is Reimagined-specific behavior - the game
stores the bonus for all three damage categories simultaneously.

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

  items:
    - name: "The Oculus"
      base_type: "Swirling Crystal [X]"
      location: "inventory"
      pos: [0, 0]
      quality: "unique"
      item_level: 64
      durability_current: 212
      durability_max: 250
      properties:
        - "25% Chance to cast level 1 Teleport when struck"
        - "+3 to Sorceress Skill Levels"
        - "+30% Faster Cast Rate"
        - "+20% Enhanced Defense"
        - "+20 to Vitality"
        - "+20 to Energy"
        - "+20% to All Resistances"
        - "+5 to Mana after each Kill"
        - "+50% Chance Items Roll Magic or Better"

    - name: "Rhyme of the Bard"
      base_type: "War Javelin [N]"
      location: "inventory"
      pos: [1, 0]
      quality: "unique"
      item_level: 99
      quantity_current: 410
      quantity_max: 410
      properties:
        - "+35% Increased Attack Speed"
        - "+212% Enhanced Weapon Damage"
        - "Increased Stack Size"
        - "Replenishes quantity"
        - "Level 2 War Cry (200/200 Charges)"
        - "Level 3 Battle Orders (200/200 Charges)"
        - "Level 3 Shout (200/200 Charges)"

    - name: "Golem's Might"
      base_type: "Ring"
      location: "inventory"
      pos: [2, 0]
      quality: "unique"
      item_level: 99
      properties:
        - "+10% Increased Attack Speed"
        - "Adds 10-15 Weapon Damage"
        - "+25 to Strength"
        - "+11% to All Resistances"
        - "+8 Life after each Kill"
```

