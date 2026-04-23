# TC18 - Ring Graphic Variants

## Summary

Six rings in the inventory to verify how graphic variant indices are stored.
Five rings represent each of the 5 standard ring appearances ("Big Blue",
"Coral", "Crown", "Orange", "Small Blue"). The sixth ring is a Unique with
a true custom graphic.

- **File:** TestSorc.d2s
- **Character:** Sorceress, Level 1
- **Goal:** Map graphic_variant_index values to visual ring appearances,
  and determine how "true custom graphics" (Unique-only) differ from
  standard random variants.

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

### Inventory Grid (10x4)
```
   C0         C1         C2         C3         C4         C5
R0 [BigBlue]  [Coral]    [Crown]    [Orange]   [SmBlue]   [Unique]
```
All rings are 1x1 in size.

### Belt, Stash, Cube
All completely empty.

## Item Details

### Item 1: Ring of the Wolf - "Big Blue" variant (Inventory 0,0)
- **Quality:** Magic
- **Item Level:** 98
- **Required Level:** 26
- **Visual Variant:** Big Blue (standard)
- **Properties:**
  - +17 to Life

### Item 2: Gnostic Ring of the Wolf - "Coral" variant (Inventory 1,0)
- **Quality:** Magic
- **Item Level:** 96
- **Required Level:** 75
- **Visual Variant:** Coral (standard)
- **Properties:**
  - +5 to Iron Maiden (Necromancer only)
  - +14 to Life

### Item 3: Loremasters Ring of Life - "Crown" variant (Inventory 2,0)
- **Quality:** Magic
- **Item Level:** 99
- **Required Level:** 26
- **Visual Variant:** Crown (standard)
- **Properties:**
  - Physical Damage Reduced by 9
  - +1 to Experience Gained

### Item 4: Garnet Ring - "Orange" variant (Inventory 3,0)
- **Quality:** Magic
- **Item Level:** 98
- **Required Level:** 13
- **Visual Variant:** Orange (standard)
- **Properties:**
  - +29% Fire Resistance

### Item 5: Ring of the Lich - "Small Blue" variant (Inventory 4,0)
- **Quality:** Magic
- **Item Level:** 97
- **Required Level:** 84
- **Visual Variant:** Small Blue (standard)
- **Properties:**
  - +8% Mana Stolen per Hit
  - +11% Life Stolen per Hit

### Item 6: Vampiric Regeneration - Unique with Custom Graphic (Inventory 5,0)
- **Quality:** Unique
- **Item Level:** 64
- **Required Level:** 28
- **Visual Variant:** True custom graphic (Unique-specific)
- **Properties:**
  - +5% Mana Stolen per Hit
  - +6% Life Stolen per Hit
  - +35 to Life
  - Replenish Life +12
  - +35% Mana Regeneration
  - Heal Stamina +20%

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
  items:
    - name: "Ring of the Wolf"
      pos: [0, 0]
      quality: "magic"
      item_level: 98
      visual_variant: "Big Blue"
      properties:
        - "+17 to Life"
    - name: "Gnostic Ring of the Wolf"
      pos: [1, 0]
      quality: "magic"
      item_level: 96
      visual_variant: "Coral"
      properties:
        - "+5 to Iron Maiden (Necromancer only)"
        - "+14 to Life"
    - name: "Loremasters Ring of Life"
      pos: [2, 0]
      quality: "magic"
      item_level: 99
      visual_variant: "Crown"
      properties:
        - "Physical Damage Reduced by 9"
        - "+1 to Experience Gained"
    - name: "Garnet Ring"
      pos: [3, 0]
      quality: "magic"
      item_level: 98
      visual_variant: "Orange"
      properties:
        - "+29% Fire Resistance"
    - name: "Ring of the Lich"
      pos: [4, 0]
      quality: "magic"
      item_level: 97
      visual_variant: "Small Blue"
      properties:
        - "+8% Mana Stolen per Hit"
        - "+11% Life Stolen per Hit"
    - name: "Vampiric Regeneration"
      pos: [5, 0]
      quality: "unique"
      item_level: 64
      visual_variant: "Custom (Unique)"
      properties:
        - "+5% Mana Stolen per Hit"
        - "+6% Life Stolen per Hit"
        - "+35 to Life"
        - "Replenish Life +12"
        - "+35% Mana Regeneration"
        - "Heal Stamina +20%"
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```

