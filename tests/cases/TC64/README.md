# TC64 - Mercenary Header + Full 10-Slot Merc Equipment

## Summary

Regression fixture for the mercenary header and the Reimagined 10-slot
merc paperdoll. The player character has no gear whatsoever - everything
interesting is equipped on the mercenary. That isolation lets the test
exercise the entire merc code path (header + jf section + full slot
set + socket children) without any player items getting in the way.

- **File:** MercOnly.d2s
- **Character:** MercOnly, a Level 80 Barbarian
- **Goal:** Verify that the merc's name, class, difficulty, experience,
  every equipped slot, and the socket children of the Circlet are
  recovered intact.

## Expected Mercenary

- **Name:** Paige? No - **Fiona** (her name table entry is different
  from Knurpsi's Rogue; this save deliberately uses a different name_id
  so the two fixtures cross-check the template math).
- **Class:** Rogue Scout, Fire variant, Normal difficulty.
- **Experience:** 62,410,000.
- **Status:** Alive.

## Expected Merc Equipment

The merc wears a full Reimagined "all ten slots" loadout:

| Slot | Item | Quality |
|------|------|---------|
| Head | **Fair Weather** (Circlet, 2 sockets) | Unique |
| Amulet | **Mara's (amu7)** | Unique |
| Body Armor | **Iceblink** (Splint Mail) | Unique |
| Right Hand | **Telena's War Bow** (Long War Bow, 2H) | Unique |
| Left Hand | empty (Long War Bow is 2H) | - |
| Right Ring | **Vampiric Regeneration** | Unique |
| Left Ring | **Vampire's Crusade** | Set |
| Belt | **Immortal King's Detail** (War Belt) | Set |
| Boots | **Sandstorm Trek** (Scarabshell Boots) | Unique |
| Gloves | **Magefist** (Light Gauntlets) | Unique |

Fair Weather's two sockets are filled with a **Rare Jewel** ("Rune
Talisman") and a **Skull** gem.

## Highlights to watch for

- Iceblink's "+1 to Warp (oskill)" - exercises the stat 97 / stat 387
  display-mirror pair.
- Immortal King's Detail's "+2 to Berserk (Barbarian Only)" - exercises
  class-specific skill resolution via hireling.txt + skills.txt.
- Sandstorm Trek's "Repairs 1 durability in 20 seconds" - exercises the
  descfunc=11 conditional template fix.
- Telena's War Bow carries Reimagined's hidden charm passive, which
  must NOT appear in any tooltip even though it lives in the raw stats.

## What this test protects

Every bug fixed during the merc feature rollout hits this save:
- Merc header parsing at offset 0xA1 (14 bytes, "no merc" detection).
- Name resolution through mercenaries.json with a non-Knurpsi name_id.
- All ten merc slots visible through `merc_equipped()`.
- Socket children correctly linked to their parent under `merc_items`.
- Display-layer fixes (Berserk, Warp, Repair formula, Hidden Charm
  suppression).
