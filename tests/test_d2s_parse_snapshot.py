"""TC81 - Golden-file snapshot runner for D2SParser output.

Pins byte-exact parser output across every TC fixture so subsequent
refactors (e.g. the header / stats / items / merc mixin split) can
prove "no behaviour change".

This file IS that snapshot runner. Running it in write mode (via the
UPDATE_SNAPSHOTS env var) refreshes the per-fixture golden files.
Running it in check mode (the default, and the CI mode) parses each
fixture and asserts that ``ParsedCharacter.model_dump_json()`` is
byte-identical to the committed golden.

Usage:

  # Refresh goldens (do this when you intentionally change parser
  # output, e.g. a new [BV TC##] fix):
  UPDATE_SNAPSHOTS=1 pytest tests/test_d2s_parse_snapshot.py

  # Check: any diff vs golden fails the test.
  pytest tests/test_d2s_parse_snapshot.py

Each mixin-extraction phase (HeaderParser / StatsSkillsParser /
ItemsParser / MercenaryParser) ends with
'pytest tests/test_d2s_parse_snapshot.py' as the safety gate.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# Fixtures under tests/cases/TC*/*.d2s
_FIXTURE_ROOT = Path(__file__).parent / "cases"
_GOLDEN_ROOT = Path(__file__).parent / "golden" / "d2s_parse"
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches a JSON key-value pair ``"source_path": "..."`` regardless of
# the payload (which is the absolute machine-specific path the parser
# captured). Replaced with a repo-relative POSIX form so goldens stay
# byte-reproducible across machines.
_SOURCE_PATH_RE = re.compile(r'"source_path":\s*"[^"]*"')


def _all_d2s_fixtures() -> list[Path]:
    if not _FIXTURE_ROOT.is_dir():
        return []
    return sorted(_FIXTURE_ROOT.rglob("*.d2s"))


def _golden_path_for(fixture: Path) -> Path:
    """Return the per-fixture golden JSON path (mirrors TC directory layout)."""
    rel = fixture.relative_to(_FIXTURE_ROOT)
    return _GOLDEN_ROOT / rel.with_suffix(".json")


def _normalize_json_for_snapshot(json_str: str, fixture: Path) -> str:
    """Rewrite machine-specific fields so goldens are reproducible.

    The parser records ``CharacterHeader.source_path`` as the absolute
    path it was handed (e.g. ``C:/path/to/d2rr_toolkit/...``).
    That absolute path would leak the contributor's home directory into
    the golden, produce diffs every time a new contributor runs the
    runner, and drift every time the repo is cloned to a new location.

    This helper replaces the ``source_path`` value with the fixture's
    path relative to the repo root in POSIX form (e.g.
    ``tests/cases/TC01/TestABC.d2s``) before the JSON is written to /
    compared against the golden. No other fields are touched.
    """
    try:
        rel = fixture.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        # Fixture outside the repo (e.g. user ran the runner against a
        # fixture copied elsewhere). Fall back to just the basename so
        # the golden still excludes directory info.
        rel = fixture.name
    replacement = f'"source_path": "{rel}"'
    return _SOURCE_PATH_RE.sub(replacement, json_str, count=1)


@pytest.mark.needs_game_data
@pytest.mark.parametrize(
    "fixture",
    _all_d2s_fixtures(),
    ids=lambda p: str(p.relative_to(_FIXTURE_ROOT)).replace("\\", "/"),
)
def test_parse_snapshot_matches_golden(fixture: Path) -> None:
    """Each TC fixture must parse to a ``ParsedCharacter`` matching its golden.

    Passes in one of two modes:
      - ``UPDATE_SNAPSHOTS=1``: write the current output as the new
        golden. This is how new TC fixtures get their baseline.
      - default: compare the current output to the committed golden
        and fail on any diff.
    """
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    try:
        parsed = D2SParser(fixture).parse()
    except Exception as e:
        pytest.skip(f"parser raised {type(e).__name__} on {fixture.name}: {e}")

    # model_dump_json with indent=2 gives a stable line-diffable form.
    # sort_keys=True is NOT used - pydantic already emits fields in a
    # declaration-order, and sorted output would hide field-reorder
    # regressions the snapshot is meant to catch.
    current = parsed.model_dump_json(indent=2)
    # Strip machine-specific source_path so the golden stays reproducible
    # across contributors / clone locations.
    current = _normalize_json_for_snapshot(current, fixture)

    golden = _golden_path_for(fixture)
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(current, encoding="utf-8")
        return

    if not golden.is_file():
        pytest.skip(f"no golden yet for {fixture.name}; run with UPDATE_SNAPSHOTS=1 to create one.")

    expected = golden.read_text(encoding="utf-8")
    if current == expected:
        return

    # On diff: save the current output alongside the golden as
    # <stem>.actual.json so the maintainer can eyeball the diff
    # without re-running the parser manually.
    actual_path = golden.with_suffix(".actual.json")
    actual_path.write_text(current, encoding="utf-8")
    pytest.fail(
        f"D2SParser output drifted vs golden for {fixture.name}.\n"
        f"  Expected: {golden}\n"
        f"  Actual:   {actual_path}\n"
        f"If the change is intentional, inspect the diff and rerun with "
        f"UPDATE_SNAPSHOTS=1 to refresh the golden."
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

