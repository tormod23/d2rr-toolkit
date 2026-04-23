# TC62 - Simple Item Padding Regression

## Summary

Targeted regression fixture for the "simple item trailing padding" parsing
path. Checks that every simple healing-, mana-, and rejuvenation-potion type
is recognised at its correct inventory position with the expected binary
footprint.

- **File:** SimpleItems.d2s
- **Goal:** Verify that all 24 simple items parse correctly and land in the
  expected grid slots, exercising every healing-potion, mana-potion, and
  rejuvenation-potion type side-by-side.

## Items

### Inventory Grid (rows 0-2)

```
   C0    C1    C2    C3    C4    C5    C6    C7    C8    C9
R0 [hp1] [hp1] [hp2] [hp2] [hp3] [hp3] [hp4] [hp4] [hp5] [hp5]
R1 [mp1] [mp1] [mp2] [mp2] [mp3] [mp3] [mp4] [mp4] [mp5] [mp5]
R2 [rvs] [rvs] [rvl] [rvl]  .     .     .     .     .     .
```

- **Row 0:** two of each Healing Potion (Minor through Full)
- **Row 1:** two of each Mana Potion (Minor through Full)
- **Row 2:** two Rejuvenation Potions and two Full Rejuvenation Potions

### Equipped / Stash / Cube
All other containers are empty in this fixture.

## What this test protects

Each pair of adjacent potions in row 0 and row 1 exercises the parser's
simple-item bookkeeping: the code pair at columns (2,0)-(3,0) and (2,1)-(3,1)
is the specific regression trigger that previously caused the parser to drop
the trailing padding byte and drift into the next item. The fixture sits
ahead of every other test because a cascade failure here corrupts anything
that follows it in a normal character save.

