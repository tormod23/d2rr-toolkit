# TC12 - Unique Ring with Custom Graphics

## Summary

Minimal character with exactly one item: a Unique Ring with custom graphics
in the inventory.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify correct parsing of a Unique ring with a custom graphic variant.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Experience:** 0
- **Gold (Inventory):** 0
- **Gold (Stash):** 0
- **All attributes:** class base, no points spent
- **Skills:** 0 invested, 0 remaining
- **Quests:** None started

## Items

### Equipped Items
ALL equipment slots are **empty**.

### Inventory Grid (10x8)
```
   C0    C1    ...
R0  [Ri]  .     ...
R1   .    .     ...
```
- **[Ri]**: Ring of Engagement (Unique) - Position: (0,0), Size: 1x1

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Ring of Engagement (Inventory 0,0)
- **Quality:** Unique
- **Item Level:** 67
- **Required Level:** 3
- **Properties:**
  - Level 1 Might Aura When Equipped
  - +2 to Maximum Weapon Damage
  - +5 to Strength
  - +17 to Life
- **Custom Graphics:** Yes (ring has alternate visual)
- **Socketed:** No
- **Ethereal:** No

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
    experience: 0
    gold_inv: 0
    gold_stash: 0
  items:
    - name: "Ring of Engagement"
      pos: [0, 0]
      quality: "unique"
      item_level: 67
      has_custom_graphics: true
      properties:
        - "Level 1 Might Aura When Equipped"
        - "+2 to Maximum Weapon Damage"
        - "+5 to Strength"
        - "+17 to Life"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```

