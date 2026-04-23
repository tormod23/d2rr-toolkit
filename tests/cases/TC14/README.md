# TC14 - Magic Small Charm

## Summary

Minimal character with exactly one item: a Magic Small Charm in the inventory.

- **File:** TestDruid.d2s
- **Character:** Druid, Level 1
- **Goal:** Verify correct parsing of a Magic charm item.

## Character Profile

- **Name:** TestDruid
- **Class:** Druid
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
R0  [SC]  ...
```
- **[SC]**: Unceasing Small Charm of Sorcery - Position: (0,0), Size: 1x1

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Unceasing Small Charm of Sorcery (Inventory 0,0)
- **Quality:** Magic
- **Item Level:** 99
- **Required Level:** 60
- **Charm Weight:** 1
- **Properties:**
  - +20 to Mana
  - +6% Cold Resistance
  - +6% Lightning Resistance
- **Socketed:** No
- **Ethereal:** No

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestDruid"
    class: "Druid"
    level: 1
  items:
    - name: "Unceasing Small Charm of Sorcery"
      pos: [0, 0]
      quality: "magic"
      item_level: 99
      properties:
        - "+20 to Mana"
        - "+6% Cold Resistance"
        - "+6% Lightning Resistance"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```

