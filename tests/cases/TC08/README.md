# TC08 - Minimal Extended Item (Leather Gloves)

## Summary

Minimal character with exactly one item: Leather Gloves in the inventory.
This is the simplest possible extended (non-simple) item - Normal quality,
no sockets, no affixes, no special flags.

- **File:** TestPaladin.d2s
- **Character:** Paladin, Level 1
- **Goal:** Verify correct parsing of a single Normal-quality armor item with defense and durability values.

## Character Profile

- **Name:** TestPaladin
- **Class:** Paladin
- **Level:** 1
- **Experience:** 0
- **Gold (Inventory):** 0
- **Gold (Stash):** 0

**Attributes (all at class base, no points spent):**
- **Strength:** 25
- **Dexterity:** 20
- **Vitality:** 25
- **Energy:** 15
- **Stat Points Remaining:** 0
- **Skill Points Remaining:** 0

**Quests:** None started.

## Items

### Equipped Items
ALL equipment slots are **empty**.

### Inventory Grid (10x8)
```
   C0    C1    ...
R0  [GL]  [GL]  ...
R1  [GL]  [GL]  ...
...
```
- **[GL]**: Leather Gloves - Position: (0,0), Size: 2x2

### Belt, Stash, Cube
All **completely empty**.

## Item Details

### Item 1: Leather Gloves (Inventory 0,0)
- **Quality:** Normal
- **Item Level:** 6
- **Defense:** 3
- **Durability:** 12 / 12
- **Position:** Inventory (0,0)
- **Size:** 2x2
- **Starter Item:** No
- **Socketed:** No
- **Ethereal:** No
- **Magical Properties:** None

> **Note on Reimagined display notation:**
> - `[N]` = Normal tier, `[X]` = Exceptional tier, `[E]` = Elite tier
> - These refer to the item tier (base type), NOT to quality or ethereal status.

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestPaladin"
    class: "Paladin"
    level: 1
    experience: 0
    gold_inv: 0
    gold_stash: 0
  items:
    - name: "Leather Gloves"
      pos: [0, 0]
      quality: "normal"
      item_level: 6
      defense: 3
      durability_max: 12
      durability_current: 12
      is_starter: false
      socketed: false
      ethereal: false
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
