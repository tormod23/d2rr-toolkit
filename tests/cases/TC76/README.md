# TC76 - Set-Quality Throwing Weapon Parsing

## Summary

Captures the minimal-reproduction case for a parser bug in
`_parse_misc_throw` (ItemsParserMixin in `d2s_parser_items.py`):
the throwing-weapon path forgot to read the 5-bit
`set_bonus_mask` for Set-quality throwing items, resulting in
properties read 5 bits early, six garbage stat reads, and 96
unconsumed bits at the end of the item that the parser
re-interpreted as a phantom 'hhwd' item.

The user (Tormod) prepared two isolated fixtures: a D2S
character file and a D2I shared stash, each containing **only**
the problematic item plus an HP1 separator so the bug can be
diagnosed without surrounding clutter.

## Fixtures

- `SetThrowingWeapon.d2s` - character with the Holy Fury Set
  Balrog Spear (`7s7`) and an HP1 health potion in stash.
- `SetThrowingWeapon.d2i` - shared stash with the same Set Spear
  + HP1 in tab 5 (the Gems/Materials/Runes page).

Both files were freshly written by the Reimagined client on
2026-04-29.

## In-game tooltip values (source of truth)

```
Holy Fury (75)
Balrog Spear [E]                           # Exceptional tier
Throw Damage:    161 to 372
One-Hand Damage: 141 to 375
Normal Attack Speed
Required Dexterity:  95
Required Strength:  127
Required Level:      64

+178% Enhanced Weapon Damage               # stat 17 + paired 18
Adds 50-200 Weapon Damage                  # stat 159 + 160 (throw) AND stat 21 + 22 (1H)
Increased Stack Size                       # stat 254
Replenishes Quantity                       # stat 253
```

Item-level set bonuses (stored on the item):

```
37% Chance to cast level 10 Chain Lightning on striking (2 Items)
+6 to Charged Strike (oskill) (3 Items)
```

The 7s7 belongs to the **"Wrath of Vengeance"** set; tier-1
through tier-4 set-level bonuses come from the set definition,
not stored on the item.

## Expected parser output

After Fix 1 (Set-quality branch in throwing-weapon path):

```
7s7:
  source_data:       53 bytes  (NOT 41 - that was the bug)
  set_bonus_mask:    3         (= 0b00011 = tier-2 + tier-3 bonuses)
  magical_properties: 9 entries
    [17]  item_maxdamage_percent       value=178
    [18]  item_mindamage_percent       value=178   (paired with 17)
    [21]  mindamage                    value=50
    [22]  maxdamage                    value=200
    [97]  item_nonclassskill           value=1
    [159] item_throw_mindamage         value=50
    [160] item_throw_maxdamage         value=200
    [253] item_replenish_quantity      value=25
    [254] item_extra_stack             value=200
  set_bonus_properties: 3 entries
    [198] item_skillonhit              skill=Chain Lightning lvl=10 chance=37%
    [97]  item_nonclassskill           skill_id=24 (Charged Strike) value=6
    [387] item_nonclassskill_display   (display variant of the oskill)
```

## What this fixture pins

`tests/test_set_throwing_weapon.py`:

  S1 - Both D2S and D2I parsers see exactly 1 7s7 item and no
        phantom items.
  S2 - 7s7 source_data is 53 bytes (size before fix: 41 bytes).
  S3 - set_bonus_mask is 3 (binary 00011).
  S4 - magical_properties contains the 9 expected stats with
        correct values matching the in-game tooltip.
  S5 - set_bonus_properties contains the Chain Lightning CTC
        and Charged Strike oskill plus its display variant.
  S6 - JM-count = parsed-item-count for tab 0 (no parser-extras
        from misalignment cascade).

## Regression class

A future regression in this area (e.g. someone removes the Set
branch from `_parse_misc_throw`) would reintroduce:

- `len(parser_items) > jm_count` (parser-extra appearance)
- 7s7 source_data shrinks back to 41 bytes
- A spurious 'hhwd' or similar 4-char-code item with
  `simple=True, runeword=True, socketed=True` flag combination
- Six garbage stats (stat IDs 35, 89, 128, 304, 341, 355)
  appearing in the magical_properties of the 7s7

Any of those is sufficient to fail this test loudly.
