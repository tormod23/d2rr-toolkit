# TC71 - Bulk Header Sample Pool

## Summary

Three small character files used by the bulk header parser tests
(`tests/test_bulk_header_parser.py`, `tests/test_character_header_fields.py`)
to verify that header-only parsing produces the same field values as a
full parse across a varied set of saves.

These characters are **NOT** referenced by any single deep-validation
TC. They exist only as a header-fields sample pool.

| File | Class | Mode | Status |
|------|-------|------|--------|
| `HCLives.d2s` | Warlock | HC | Level 1, alive |
| `HCDied.d2s`  | Warlock | HC | Level 1, permanently dead |
| `StraFoHdin.d2s` | Paladin | SC | Patriarch |

## Why a separate TC?

The bulk header tests need a handful of distinct headers (mode/class/
status combinations) that are not interesting enough to deserve their
own dedicated TC. Pooling them here keeps the test fixtures discoverable
and prevents loose `*.d2s` files from drifting around the repo root.
