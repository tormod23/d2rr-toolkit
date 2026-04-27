# TC10 - Leather Gloves with Reduced Durability

## Summary

Follow-up to TC08 with the same item type (Leather Gloves) but with different
current durability (10 instead of 12). This allows independent verification
of max and current durability since TC08 had both values identical (12/12).

- **File:** TestPaladin.d2s
- **Character:** Paladin (same as TC08/TC09), Level 1
- **Goal:** Verify parsing of an armor item where current durability differs from max durability.

## Character Profile

Identical to TC08:
- **Name:** TestPaladin
- **Class:** Paladin
- **Level:** 1, Experience: 0, Gold: 0
- **All attributes:** class base, no points spent
- **Skills:** 0 invested
- **Quests:** None started

## Items

### Inventory Grid
```
   C0    C1    ...
R0  [GL]  [GL]  ...
R1  [GL]  [GL]  ...
```
- **[GL]**: Leather Gloves - Position: (0,0), Size: 2x2

### Belt, Stash, Equipped, Cube
All completely empty.

## Item Details

### Item 1: Leather Gloves (Inventory 0,0)
- **Quality:** Normal
- **Item Level:** 6
- **Defense:** 2 (different from TC08 which had Defense 3 - same item type, different roll)
- **Durability:** 10 current / 12 max
- **Position:** Inventory (0,0)
- **Starter Item:** No
- **Socketed:** No
- **Ethereal:** No

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestPaladin"
    class: "Paladin"
    level: 1
  items:
    - name: "Leather Gloves"
      pos: [0, 0]
      quality: "normal"
      item_level: 6
      defense: 2
      durability_max: 12
      durability_current: 10
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
