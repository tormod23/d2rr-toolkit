# TC09 - Short Sword (Weapon Item)

## Summary

Same character as TC08 (Paladin, Level 1), but with a Short Sword instead of
Leather Gloves. This tests weapon-type item parsing. The sword has a distinctive
durability value of 250/250 to make verification easier.

- **File:** TestPaladin.d2s
- **Character:** Paladin (same as TC08), Level 1
- **Goal:** Verify correct parsing of a weapon item with durability and damage values.

## Character Profile

Same as TC08:
- **Name:** TestPaladin
- **Class:** Paladin
- **Level:** 1, Experience: 0, Gold: 0
- **All attributes:** at class base, no points spent
- **Skills:** 0 invested, 0 remaining
- **Quests:** None started

## Items

### Equipped Items
ALL slots empty.

### Inventory Grid
```
   C0    ...
R0  [SS]  ...
R1  [SS]  ...
R2  [SS]  ...
```
- **[SS]**: Short Sword - Position: (0,0), Size: 1x3

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Short Sword (Inventory 0,0)
- **Quality:** Normal
- **Item Level:** 6
- **One-Hand Damage:** 2 to 7
- **Durability:** 250 / 250
- **Position:** Inventory (0,0)
- **Size:** 1x3
- **Starter Item:** No
- **Socketed:** No
- **Ethereal:** No
- **Magical Properties:** None

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestPaladin"
    class: "Paladin"
    level: 1
  items:
    - name: "Short Sword"
      pos: [0, 0]
      quality: "normal"
      item_level: 6
      damage_min: 2
      damage_max: 7
      durability_max: 250
      durability_current: 250
      is_starter: false
      socketed: false
      ethereal: false
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
