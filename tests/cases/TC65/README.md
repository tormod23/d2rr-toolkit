# TC65 - Horadric Cube Contents

## Summary

Regression fixture for the Horadric Cube content path. Until this save
was added, not a single TC contained items stored inside a cube, so the
`panel_id=4` code path was completely untested by the automated suite.

- **File:** CubeContents.d2s
- **Character:** CubeContents, a Level 1 Paladin
- **Goal:** Verify that a Horadric Cube in the inventory plus every
  item stored inside it parse cleanly, including a 4-socket runeword
  that lives inside the cube.

## Expected Inventory

A single item: the **Horadric Cube** at position (0, 0). Nothing else
is in the character's inventory, stash, belt, or equipment.

## Expected Cube Contents

15 primary items plus 4 rune children inside the runeword weapon:

| Pos | Item | Quality | Notes |
|-----|------|---------|-------|
| (0, 0) | **Natalya's Totem** (Grim Helm) | Set | Adds 25-50 damage set bonus active |
| (2, 0) | **Grimoire of the Riven Blade** | Unique | Warlock book, grants a Might aura |
| (11, 0) | **Fleshbleeder** (Tulwar) | Unique | |
| (0, 2) | **Insight** (Thresher, 4 sockets) | Runeword | Ral + Tir + Tal + Sol |
| (2, 2) | **Western Worldstone Shard** | Normal | quest item, no properties |
| (2, 3) | **Key of Terror** | Normal | quest item, no properties |
| (0, 6) | **Talic's Anguish** | Normal | quest item, no properties |
| (11, 3) | **Identify Scroll** | Simple | |
| (11, 4) | **Minor Rejuvenation Potion (35%)** | Simple | |
| (10, 5) | **Antidote Potion** | Simple | |
| (11, 5) | **Full Rejuvenation Potion** | Simple | |
| (10, 6) | **Thawing Potion** | Simple | |
| (11, 6) | **Shadow Eye** (Rare Jewel) | Rare | |
| (10, 7) | **Town Portal Scroll** | Simple | |
| (11, 7) | **Collin's Destruction** (Small Charm) | Unique | Charm Weight: 1, Splash 100% |

## Highlights to watch for

- **Insight** is a Reimagined runeword with the recipe Ral+Tir+Tal+Sol.
  The row index in `runes.txt` does NOT match vanilla D2 (where the
  same row might be another name), so the display layer must resolve
  the name via the rune recipe, not the runeword_id row index.
- **Western Worldstone Shard**, **Key of Terror**, and **Talic's
  Anguish** are Reimagined quest items with zero magical properties -
  the parser must handle their empty property list cleanly.
- **Collin's Destruction** is a Reimagined charm whose only visible
  stats are "Charm Weight: 1" and the splash-damage passive. Every
  Reimagined weapon in this cube also carries the hidden charm passive,
  which must stay in the raw data for round-trip but never display.

## What this test protects

- The Horadric Cube's own item lives in the inventory with `panel_id=1`.
  Its contents live in the same `items` list but with `panel_id=4`.
  No TC ever covered `panel_id=4` before this save.
- A runeword inside the cube has exactly the same binary shape as a
  runeword in the inventory; the cube panel does not alter parsing.
- Quest items with empty property lists must not crash the parser or
  swallow any following items.
- The mixed item variety (normal, simple, rare, set, unique, runeword,
  quest, potions, scrolls) covers nearly every item kind the parser
  has to handle in a single fixture.

