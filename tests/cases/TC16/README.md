# TC16 - Three Reimagined Tool Items

## Summary

Minimal character with three Reimagined-specific tool items in the inventory.
All three are Normal quality Reimagined-specific tool items.
This tests item boundary detection when multiple tool items are adjacent.

- **File:** TestAssa.d2s
- **Character:** Assassin, Level 1
- **Goal:** Verify item boundaries for Normal-quality tool items.

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
   C0    C1    C2    ...
R0  [RP]  [JP]  [GC]  ...
```
- **[RP]**: Rune Pliers - Position: (0,0)
- **[JP]**: Jewel Pliers - Position: (1,0)
- **[GC]**: Gem Cluster - Position: (2,0)

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Rune Pliers (Inventory 0,0)
- **Quality:** Normal
- **Properties:** Returns Socketed Runes From Weapons and Armor

### Item 2: Jewel Pliers (Inventory 1,0)
- **Quality:** Normal
- **Properties:** Returns Socketed Items From Weapons and Armor

### Item 3: Gem Cluster (Inventory 2,0)
- **Quality:** Normal
- **Properties:** Combines leftover Gems into Flawless Gems

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestAssa"
    class: "Assassin"
    level: 1
  items:
    - name: "Rune Pliers"
      pos: [0, 0]
      quality: "normal"
    - name: "Jewel Pliers"
      pos: [1, 0]
      quality: "normal"
    - name: "Gem Cluster"
      pos: [2, 0]
      quality: "normal"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```

