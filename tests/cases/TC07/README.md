# TC07 - Minimal Character, Single Belt Item

## Summary

Minimal character with exactly one item: a single Minor Healing Potion in the belt,
bought from Akara (not a starter item). All other slots are empty.

- **File:** TestAmazon.d2s
- **Character:** Amazon, Level 1
- **Goal:** Verify correct parsing of a single belt potion on a minimal character. Confirm that a bought potion is not flagged as a starter item.

## Character Profile

### Statistics

- **Name:** TestAmazon
- **Class:** Amazon
- **Level:** 1
- **Experience:** 0
- **Gold (Inventory):** 0
- **Gold (Stash):** 0

**Attributes (all at class base, no points spent):**
- **Strength:** 20
- **Dexterity:** 25
- **Vitality:** 20
- **Energy:** 15
- **Stat Points Remaining:** 0
- **Skill Points Remaining:** 0

### Quest Log
- **Act 1, Quest 1 (Den of Evil):** Started (talked to Akara to buy the potion)
- All other quests: uninitiated

## Items

### Equipped Items
ALL equipment slots are **empty**.

### Inventory Grid
**Completely empty.**

### Belt Grid (4x1)
- **Slot 0:** Minor Healing Potion - bought from Akara (NOT a starter item)
- **Slot 1-3:** Empty

### Personal Stash
**Completely empty.**

## Item Details

### Item 1: Minor Healing Potion (Belt Slot 0)
- **Quality:** Normal
- **Position:** Belt, Slot 0
- **Starter Item:** No (bought from vendor)

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestAmazon"
    class: "Amazon"
    level: 1
    experience: 0
    gold_inv: 0
    gold_stash: 0
    unused_stats: 0
    unused_skills: 0
  items:
    - name: "Minor Healing Potion"
      location: "belt"
      belt_slot: 0
      quality: "normal"
      is_starter: false
  inventory_empty: true
  stash_empty: true
  equipped_empty: true
  quest_act1_q1: "started"
```

