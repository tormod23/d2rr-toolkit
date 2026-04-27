# TC17 - Buckler (Shield Item)

## Summary

Minimal character with a single Magic Buckler in the inventory.
This tests whether shields have additional type-specific fields
(e.g. block chance) beyond the standard armor defense + durability.

- **File:** TestNecro.d2s
- **Character:** Necromancer, Level 1
- **Goal:** Verify shield-specific field layout in extended item data.

## Character Profile

- **Name:** TestNecro
- **Class:** Necromancer
- **Level:** 1
- **Experience:** 0
- **Gold (Inventory):** 0
- **Gold (Stash):** 0
- **All attributes:** class base, no points spent
- **Skills:** 0 invested, 0 remaining

## Items

### Equipped Items
ALL equipment slots are **empty**.

### Inventory Grid (10x8)
```
   C0    C1    ...
R0  [Bu]  [Bu]  ...
R1  [Bu]  [Bu]  ...
```
- **[Bu]**: Buckler of Blocking - Position: (0,0), Size: 2x2

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Buckler of Blocking (Inventory 0,0)
- **Quality:** Magic
- **Item Level:** 6
- **Defense:** 6
- **Chance to Block:** 33% (modified by properties, base value may differ)
- **Durability:** 12 / 12
- **Required Strength:** 12
- **Properties:**
  - +15% Faster Block Rate
  - +13% Increased Chance of Blocking

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestNecro"
    class: "Necromancer"
    level: 1
  items:
    - name: "Buckler of Blocking"
      pos: [0, 0]
      quality: "magic"
      item_level: 6
      defense: 6
      durability_max: 12
      durability_current: 12
      properties:
        - "+15% Faster Block Rate"
        - "+13% Increased Chance of Blocking"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
