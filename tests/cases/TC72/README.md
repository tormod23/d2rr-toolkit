# TC72 - Charm affix ID decoding for has_gfx=1 items

## Summary

VikingBarbie live-save fixture used to pin the D2S parser's carry-chain
compensation for `has_gfx=1` Magic-quality charms (cm1 / cm2 / cm3).
The fixture is a frozen copy of the live save from the game directory at
the time the bug was diagnosed; it contains 30 charms that span every
`has_auto_prefix=True, bf1=False` automod / carry-bit combination in
Reimagined 3.0.7.

## In-game verification points

Grand Charms (cm3) in the personal stash, each tooltip cross-checked
against the live game on 2026-04-18:

| Prefix | Suffix | Stat | Notes |
|--------|--------|------|-------|
| Coral | of Balance | +25% Lightning Resistance | max roll of Coral's 21-25 range |
| Coral | of Substinence | +24% Lightning Resistance | mid-range roll |
| Coral | of Substinence | +21% Lightning Resistance | min-range roll |
| Garnet | of Dexterity | +22% Fire Resistance | mid-range Garnet 21-25 |
| Ruby | of Incineration | +26% Fire Resistance | min-range Ruby 26-30 |
| Cobalt | (no suffix) | +25% Cold Resistance | max-range Cobalt 21-25 |

The previous parser had mis-identified all three "Coral" prefixes as
"Amber" (the next magicprefix.txt row), the "Garnet" as "Ruby", and the
"Cobalt" as "Sapphire". The affix IDs were consistently one row too high
whenever the carry-bit came from a field other than `has_class`.

## What the parser was getting wrong

For magic-quality items with `has_gfx=1`, D2R packs the 12-bit affix
index across two fields: the low 10 bits live in the 11-bit `prefix_id`
slot, and the top bit is carried in the field that precedes it in the
stream. The pre-existing formula assumed that carry bit was always
`has_class`, which is correct for items that skip the 11-bit automod
read (jewels / rings / amulets). For items that DO read automod
(charms, tools, orbs, and bf1=True weapons/armor with no auto-prefix
but has_class=1), the automod slot itself absorbs the carry: its 11-bit
field stores `[10-bit real automod, 1-bit prefix carry]`.

Without the fix, `automagic.txt` lookups also collided: real automod IDs
22 ("Shimmering") and 23 ("Rainbow") were being read as 1046 and 1047,
well past the 71-row table.

## Covered by

`tests/test_charm_affix_decoding.py`
