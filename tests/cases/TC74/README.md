# TC74 - Section 6 (Reimagined audit-block) invariance under item ops

## Summary

Five game-written `.d2i` snapshots captured in a controlled in-game
sequence to characterise how the Reimagined v105 audit-block (the
seventh "page" of the SharedStash, marker `0xC0EDEAC0` instead of `JM`)
responds to ordinary item add / remove / move operations.

All five fixtures use the same character and the same item type
(`hp5`, a Reimagined healing potion) so the only variable across
snapshots is the item layout itself.

| File | Stash state |
|------|-------------|
| `Section6Invariance.d2i.A` | Truly empty - all 6 tabs hold zero items. |
| `Section6Invariance.d2i.B` | A + 1 hp5 in Tab 0. |
| `Section6Invariance.d2i.C` | B + 1 hp5 in Tab 1 (so Tabs 0 and 1 each hold 1 hp5). |
| `Section6Invariance.d2i.D` | C with the Tab 1 hp5 removed (back to a single hp5 in Tab 0). |
| `Section6Invariance.d2i.E` | D with the hp5 moved from Tab 0 to Tab 2. |

## Headline finding

**Section 6 is byte-identical across all five files.** Adding,
removing, or moving an item does NOT change the audit-block. Every
byte of the trailing `0xC0EDEAC0` page - sub-header, records,
per-tab footer - is preserved verbatim by the game across the
sequence.

This invariant is the basis for the toolkit's verbatim-preservation
strategy in `src/d2rr_toolkit/writers/d2i_writer.py`: as long as the
writer copies the audit page byte-for-byte from the source into the
output, item-level edits cannot put the file out of sync with the
audit-block contents.

## Implications

- Records inside the audit block do NOT track per-item history. They
  must come from some other game-internal event source (vendor
  interactions, multiplayer events, character progression, etc.) -
  things that happen during gameplay rather than during stash edits.
- The user-reported "Failed to join Game" error after toolkit-driven
  archive operations is **not** caused by stale Section 6 references.
  Investigating that class of failure should look elsewhere (page
  header internals, item bit-stream alignment, file-size consistency).
- The toolkit's `D2IWriter` does not need a Section 6 updater. The
  existing verbatim-copy path is sufficient and provably correct
  against this fixture set.

## Verification

The dedicated test `tests/test_section6_invariance.py` asserts
byte-identical Section 6 bytes across A-E and is part of the
regression suite. Any future change to the toolkit's writer or to the
underlying parsing path that would alter the audit page on a passive
round-trip will fail loud against this fixture set.
