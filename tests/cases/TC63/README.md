# TC63 - Superior Socketed Weapon with Enchantments

## Summary

Regression fixture for the extended-header "automod slot" path on a
non-magical weapon. Verifies a Superior Crystal Sword that has been
socketed to full capacity, filled with four Hel runes plus two jewels,
and carries the full 5-of-5 Enchantment payload supported by Reimagined.

- **File:** Knurpsi.d2s
- **Character:** Knurpsi, a low-level Necromancer
- **Goal:** Verify all 41 top-level items plus their socket children parse
  correctly, with the Superior Crystal Sword at inventory (0,0) round-tripping
  every displayed stat.

## Expected Item at Inventory (0,0)

```
Superior Crystal Sword [N]
'HelHelHelHel'
One-Hand Damage: 5 to 16
Durability: 200 of 250
Required Strength: 9
Enchantments: 5 / 5
+13% Enhanced Weapon Damage
+2 to Attack Rating
Adds 63-511 Weapon Fire Damage
Adds 63-511 Weapon Lightning Damage
Adds 63-511 Weapon Cold Damage
+40 Weapon Poison Damage over 2 seconds
+6 Defense
+3 Life after each Kill
+4 to Mana after each Kill
Attacker Takes Damage of 100
Requirements Reduced By -80%
Socketed (6)
```

The item is Superior (quality tier Normal), NOT a runeword - the
`'HelHelHelHel'` line is the generic "socketed contents" display showing
the four Hel runes inserted side-by-side, not a runeword name.

## Character Inventory Highlights

- 9x Minor Healing Potion stacked in the right-hand inventory column -
  many of them sit directly next to each other, exercising the simple-item
  padding path that TC62 also covers.
- Horadric Cube, two books, ring, amulet, small charms, a belt full of
  potions, a handful of gems, and the Crystal Sword described above.

## What this test protects

The Crystal Sword is the only base weapon type where the parser's original
automod-slot handling was incorrect. If the 11-bit slot is read at the wrong
offset, the displayed durability collapses to nonsense values, the socket
count drops from six to one, and every trailing magical property is dropped
- which in turn cascades into garbage when the parser tries to continue to
the next item. Keeping this item stable guards the entire extended-header
code path against a whole class of silent drift bugs.

