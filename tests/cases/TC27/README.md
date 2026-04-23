# TC27 - Enchanted Items

## Summary

Sorceress with three enchanted items in inventory: two Normal-quality weapons
(1 and 3 enchantments) and one Unique socketed helm (3 enchantments, 4 Um runes).
Tests the Reimagined enchantment system.

- **File:** TestSorc.d2s
- **Character:** TestSorc, Sorceress, Level 1
- **Goal:** Verify enchantment counter storage and enchanted property parsing.

## Items

### Item 1: Scimitar [N] - "1 of 5 Enchantments"
- **Position:** Inventory (0,0)
- **Quality:** Normal
- **Item Level:** 6
- **Durability:** 250/250
- **Enchantments:** 1/5
- **Properties:**
  - +30% Extra Gold from Monsters
  - +15% Chance Items Roll Magic or Better

### Item 2: Spear [N] - "3 of 10 Enchantments"
- **Position:** Inventory (1,0)
- **Quality:** Normal
- **Item Level:** 6
- **Durability:** 250/250
- **Enchantments:** 3/10
- **Properties:**
  - +14% Increased Attack Speed
  - +7% Faster Cast Rate

### Item 3: Bane's Dark Wisdom - Shako [E], Unique, 4 Sockets, 3 Enchantments
- **Position:** Inventory (3,0)
- **Quality:** Unique
- **Item Level:** 99
- **Defense:** 120
- **Durability:** 12/12
- **Socketed:** Yes (4 sockets, all filled with Um runes)
- **Enchantments:** 3/3
- **Properties:**
  - +5 to All Skills
  - +119 Defense (from Unique table)
  - +60% to All Resistances (from Unique table)
  - +20% to Experience Gained
  - -4 to Light Radius
  - Socketed (4)
- **Note:** Unique item's inherent stats (+119 Defense, +60% All Res) come from
  the Unique item table lookup, NOT from the item's own property list.

## Enchantment System

Enchantment counts are tracked per item slot category:

| Item Category | Max Enchants |
|:--------------|:-------------|
| Jewelry (Rings, Amulets) | 2 |
| Helms, Gloves, Belts, Boots | 3 |
| Shields, Body Armor, 1H Weapons | 5 |
| 2H Weapons | 10 |

Enchantment bonuses are stored as normal magical properties alongside any other
item properties. There is no separate enchant data section.

