# Test layout

Short map of where things live and why.

## Two TC directories, two purposes

| Directory | Role | Contents |
|---|---|---|
| [`cases/TCxx/`](cases/) | **Input fixtures + human docs** - one directory per test case | `README.md` describing the scenario + the binary fixture (`*.d2s`, `*.d2i`, or variant suffixes like `*.d2s.GAME` / `*.d2s.GUI`). |
| [`golden/d2s_parse/TCxx/`](golden/d2s_parse/) | **Expected parser output** - snapshot goldens for the D2S parser regression runner | `TestABC.json` = `ParsedCharacter.model_dump_json(indent=2)` captured from a known-good parse. Byte-diffed against fresh parser output by [`test_d2s_parse_snapshot.py`](test_d2s_parse_snapshot.py). |

**The two are orthogonal. Do not merge them.** Fixtures are inputs; goldens are outputs. Keeping them side-by-side in one directory would make the "what is the canonical input / expected output here?" question ambiguous, and would break the simple one-subdir-per-fixture layout the snapshot test relies on.

### Why the TC counts differ

- `cases/` has **every** TC (TC01 ... TC73). Every test case needs a fixture.
- `golden/d2s_parse/` has only the TCs that snapshot a **single canonical `.d2s` character file**. TCs that are pure shared-stash (`.d2i`) scenarios, multi-variant writer-bug repros (`.d2s.GAME` / `.d2s.GUI` etc.), or don't have a canonical character file do not appear there - they're covered by other test paths (round-trip suite, writer-specific tests).

## Key test entry points

| File | What it does |
|---|---|
| [`test_d2s_parse_snapshot.py`](test_d2s_parse_snapshot.py) | Golden-file regression: parses every `.d2s` fixture in `cases/**`, compares against `golden/d2s_parse/**`. `UPDATE_SNAPSHOTS=1` refreshes the goldens. Marked `@needs_game_data`, skipped in CI. |
| [`test_roundtrip_all_fixtures.py`](test_roundtrip_all_fixtures.py) | Byte-level parse -> write round-trip safety net across every fixture. Runs as a script. |
| [`test_d2i_parser_no_phantom_tabs.py`](test_d2i_parser_no_phantom_tabs.py) | Pins the signature-driven section walk - no phantom 7th tab from trailing metadata. |
| [`test_database_modes.py`](test_database_modes.py) | DB-path + SC/HC isolation helpers. Runs as a script. |
| [`test_cli_sc_hc_isolation.py`](test_cli_sc_hc_isolation.py) | End-to-end CLI archive SC/HC isolation. Runs as a script. |
| [`verification/`](verification/) | Ad-hoc pre-2026-04-11 verification scripts. `pyproject.toml` excludes this dir from ruff. Not part of the shipped test suite; kept for historical reference. |

## What's gitignored and why

- `*_output.txt` - scratch stdout/stderr captures from the old `verification/` scripts. Regenerated locally on demand, never committed.
- `tests/golden/**/*.actual.json` - per-fixture actual-output dumps the snapshot runner writes next to a diffed golden on failure. Disposable.

## Adding a new TC

1. Create `cases/TCNN/` with your fixture file(s) + a `README.md` describing the scenario.
2. If the fixture is a canonical `.d2s` character file and you want it in the parser snapshot runner, run `UPDATE_SNAPSHOTS=1 pytest tests/test_d2s_parse_snapshot.py::test_parse_snapshot_matches_golden[TCNN/YourChar.d2s]` to create the matching golden under `golden/d2s_parse/TCNN/`.
3. Run [`test_roundtrip_all_fixtures.py`](test_roundtrip_all_fixtures.py) - every fixture must round-trip byte-exact.
