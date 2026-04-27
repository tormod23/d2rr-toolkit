# TC15 - Jewel Pliers (Reimagined Tool Item)

## Summary

Minimal character with exactly one item: a Jewel Pliers tool in the inventory.
This is a Reimagined-specific utility item that tests parsing of Normal quality
misc items.

- **File:** TestAssa.d2s
- **Character:** Assassin, Level 1
- **Goal:** Verify parsing of Reimagined tool items.

## Character Profile

- **Name:** TestAssa
- **Class:** Assassin
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
   C0    ...
R0  [JP]  ...
```
- **[JP]**: Jewel Pliers - Position: (0,0), Size: 1x1

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Jewel Pliers (Inventory 0,0)
- **Quality:** Normal (tool item)
- **Properties:**
  - Returns Socketed Items From Weapons and Armor
  - Does not Work on Runewords
- **Note:** These are descriptive text properties, not stat-based bonuses.

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestAssa"
    class: "Assassin"
    level: 1
  items:
    - name: "Jewel Pliers"
      pos: [0, 0]
      quality: "normal"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
