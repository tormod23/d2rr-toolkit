# TC13 - Magic Amulet without Custom Graphics

## Summary

Minimal character with exactly one item: a Magic Amulet without custom graphics.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Verify correct parsing of a Magic amulet without custom graphics.

## Character Profile

- **Name:** TestSorc
- **Class:** Sorceress
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
R0  [Am]  ...
```
- **[Am]**: Bronze Amulet of the Sentinel - Position: (0,0), Size: 1x1

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Bronze Amulet of the Sentinel (Inventory 0,0)
- **Quality:** Magic
- **Item Level:** 20
- **Required Level:** 12
- **Properties:**
  - +20 to Attack Rating
  - Magic Damage Reduced By 4
- **Custom Graphics:** No
- **Socketed:** No
- **Ethereal:** No

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    - name: "Bronze Amulet of the Sentinel"
      pos: [0, 0]
      quality: "magic"
      item_level: 20
      has_custom_graphics: false
      properties:
        - "+20 to Attack Rating"
        - "Magic Damage Reduced By 4"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```
