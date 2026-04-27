# TC66 - Cube Contents Parse/Write Regression

## Summary

Three snapshots of the same `CubeContents.d2s` save used as a regression
fixture for the writer's checksum + timestamp handling and the parser's
inter-item padding capture (see commit history around `_skip_inter_item_padding`
and `writers/checksum.py`).

| File | Role |
|------|------|
| `CubeContents.d2s.original` | Untouched save written by the game. |
| `CubeContents.d2s.defect`   | A version produced by an earlier writer with a stale timestamp at offset 0x20 - the in-game symptom is that the save loads but the "last played" time is wrong. |
| `CubeContents.d2s.correct`  | The same modification re-written by the fixed writer (timestamp patched). |

## Cross-references

- `src/d2rr_toolkit/writers/checksum.py` - `[BINARY_VERIFIED TC66]`
  for the timestamp-touch requirement.
- `src/d2rr_toolkit/writers/d2i_writer.py` - `[FIX TC66 v2]` note in
  `_splice_section`.
