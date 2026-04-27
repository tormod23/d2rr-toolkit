# TC68 - GUI Roundtrip Snapshot (Cube + Stash)

## Summary

A pair of `.GUI` snapshot files captured directly after the GUI wrote
back a modified character + shared stash. They are exercised by the
roundtrip safety net (`tests/test_roundtrip_all_fixtures.py`):

  * `CubeContents.d2s.GUI`
  * `ModernSharedStashSoftCoreV2.d2i.GUI`

For each file the test runs the passive roundtrip (parse -> write ->
byte-identical) and the active roundtrip (forced rebuild for D2S /
splice path for D2I, tolerating only the checksum + timestamp delta).

## Why keep them?

Each `.GUI` snapshot pins down the exact byte layout the GUI produced
at a known-good moment. Any future regression that subtly changes the
writer output for these files will be caught immediately by the safety
net - the snapshots act as a contract between the toolkit and the GUI
consumer.

## Companion TCs

  * **TC67** - earlier GUI snapshot pair (with `.GAME` companions for
    in-game verification).
  * **TC69** - successor snapshot with a `.GUI2` variant for the
    multi-write regression on grid-tab splice.
