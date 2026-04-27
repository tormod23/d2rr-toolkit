#!/usr/bin/env python3
"""Regression suite for the Reimagined rune cube-up operation.

Covers both the low-level synthesizer (``synthesize_simple_item_blob``)
and the high-level cube-up operations (``cube_up_single``,
``cube_up_bulk``, ``cube_up_file_*``).

## Test matrix

  Section A - Synthesizer byte-exactness
    A.1 synthesizer output matches every TC61 rune template byte-for-byte
    A.2 synthesizer rejects invalid codes
    A.3 synthesizer respects display_quantity bounds

  Section B - cube_up_single
    B.1 happy path: r01 pairs=2 -> removes 4, adds 2 r02
    B.2 r33 raises CannotUpgradeMaxRuneError
    B.3 not enough input raises NotEnoughRunesError
    B.4 stack-cap overflow raises StackCapExceededError

  Section C - cube_up_bulk
    C.1 cascading: r01 -> r02 -> r03 within one call
    C.2 min_keep floor is respected
    C.3 stack cap reports via capped_by_output_limit (no raise)

  Section D - File-level integration
    D.1 cube_up_file_single produces a valid parseable .d2i
    D.2 cube_up_file_single creates a backup by default
    D.3 re-parsed file round-trips byte-exact through D2IWriter splice
    D.4 CLI rune + bulk subcommands emit exit code 0 on success
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "cases"
_TC61 = _FIXTURE_ROOT / "TC61" / "MixedSection5.d2i"


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Warm the parser's lazy game-data load before the rest of the module.

    We deliberately do NOT call ``_load_game_data`` (which eagerly loads
    every database including properties / sets / catalog) because that
    perturbs the parser's own on-demand loader ordering and produces
    subtly different parse output - e.g. ``unique_type_id`` values drift
    by ~1 vs the snapshot goldens in other test modules.

    Instead we trigger the parser's own minimal auto-load path by
    parsing any ``.d2s`` fixture. The parser then loads exactly the
    four databases it needs (item_types, item_stat_cost, skills,
    charstats) and subsequent D2IParser calls reuse those singletons.
    """
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    probe = next(_FIXTURE_ROOT.rglob("*.d2s"), None)
    if probe is None:
        pytest.skip("No .d2s fixture available to bootstrap game data.")
    if get_item_type_db().is_loaded():
        # Already loaded by a prior test module - nothing to do.
        return
    try:
        D2SParser(probe).parse()
    except Exception:
        # The parser raises if the Reimagined install is absent.
        pytest.skip("Reimagined Excel base not resolvable (no D2RR install).")


@pytest.fixture
def tmp_stash(tmp_path: Path) -> Path:
    """Copy TC61/MixedSection5.d2i into a writable tempfile and return its path."""
    target = tmp_path / "stash.d2i"
    shutil.copy2(_TC61, target)
    return target


# --------------------------------------------------------------------------- #
#  Section A: synthesizer byte-exactness
# --------------------------------------------------------------------------- #


def test_A1_synthesizer_byte_exact_against_tc61_templates():
    """Every r## in TC61 must round-trip synthesizer == template."""
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.item_utils import synthesize_simple_item_blob

    sh = D2IParser(_TC61).parse()
    rune_codes = {f"r{i:02d}" for i in range(1, 34)}
    checked = 0
    for it in sh.tabs[5].items:
        code = (it.item_code or "").lower()
        if code not in rune_codes:
            continue
        assert it.source_data is not None, f"missing source_data for {code}"
        synth = synthesize_simple_item_blob(
            code,
            display_quantity=it.display_quantity,
            is_quantity_item=True,
            position_x=it.flags.position_x,
            position_y=it.flags.position_y,
            panel_id=it.flags.panel_id,
            location_id=it.flags.location_id,
            equipped_slot=it.flags.equipped_slot,
            identified=it.flags.identified,
        )
        assert synth == it.source_data, (
            f"synthesized blob for {code} differs from game-written template.\n"
            f"  template: {it.source_data.hex(' ')}\n"
            f"  synth:    {synth.hex(' ')}"
        )
        checked += 1
    assert checked >= 7, f"expected >=7 rune templates in TC61, got {checked}"


def test_A2_synthesizer_rejects_invalid_codes():
    """Codes not in HUFFMAN_TABLE must raise ValueError."""
    from d2rr_toolkit.writers.item_utils import synthesize_simple_item_blob

    # Underscore isn't in the Huffman table (see constants.py:537).
    with pytest.raises(ValueError, match="no Huffman encoding"):
        synthesize_simple_item_blob("r_1", is_quantity_item=False)


def test_A3_synthesizer_rejects_bad_quantity():
    """display_quantity outside [1, 99] must raise."""
    from d2rr_toolkit.writers.item_utils import synthesize_simple_item_blob

    with pytest.raises(ValueError, match="out of range"):
        synthesize_simple_item_blob("r01", display_quantity=0, is_quantity_item=True)
    with pytest.raises(ValueError, match="out of range"):
        synthesize_simple_item_blob("r01", display_quantity=100, is_quantity_item=True)


# --------------------------------------------------------------------------- #
#  Section B: cube_up_single
# --------------------------------------------------------------------------- #


def test_B1_single_happy_path():
    """cube_up_single consumes pairs*2 input runes and produces pairs output."""
    from d2rr_toolkit.operations.rune_cube_up import (
        count_runes_in_section5,
        cube_up_single,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(_TC61).parse()
    pre = count_runes_in_section5(sh)
    assert pre.get("r01", 0) >= 4, "TC61 precondition: at least 4 r01 present"

    res = cube_up_single(sh, "r01", pairs=2)
    post = count_runes_in_section5(sh)

    assert res.removed == {"r01": 4}
    assert res.added == {"r02": 2}
    assert post.get("r01", 0) == pre["r01"] - 4
    assert post.get("r02", 0) == 2


def test_B2_zod_raises():
    """r33 cannot be upgraded."""
    from d2rr_toolkit.operations.rune_cube_up import (
        CannotUpgradeMaxRuneError,
        cube_up_single,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(_TC61).parse()
    with pytest.raises(CannotUpgradeMaxRuneError):
        cube_up_single(sh, "r33", pairs=1)


def test_B3_not_enough_raises():
    """Requesting more pairs than available raises NotEnoughRunesError."""
    from d2rr_toolkit.operations.rune_cube_up import (
        NotEnoughRunesError,
        cube_up_single,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(_TC61).parse()
    # TC61 has 9 r01; 100 pairs would need 200.
    with pytest.raises(NotEnoughRunesError):
        cube_up_single(sh, "r01", pairs=100)


def test_B4_stack_cap_raises():
    """Creating an output stack that would exceed 99 raises."""
    from d2rr_toolkit.operations.rune_cube_up import (
        StackCapExceededError,
        cube_up_single,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.item_utils import clone_with_quantity

    sh = D2IParser(_TC61).parse()
    # Pre-condition the tab: replace r01 with a 9-rune stack + also create
    # a near-cap r02 stack so cubing would push it past 99.
    tab5 = sh.tabs[5]
    r01_items = [it for it in tab5.items if it.item_code == "r01"]
    assert r01_items, "TC61 must contain r01"
    # Bump r01 to 50 to allow a cube without input-shortage
    r01_clone = clone_with_quantity(r01_items[0], 50)
    idx = tab5.items.index(r01_items[0])
    tab5.items[idx] = r01_clone
    # Inject an r02 synth stack with 95 count (using operation's internal synthesizer)
    from d2rr_toolkit.operations.rune_cube_up import _synthesize_rune_parsed_item

    tab5.items.append(_synthesize_rune_parsed_item("r02", display_quantity=95))
    # Now cubing 10 pairs of r01 -> 10 r02 would push r02 from 95 to 105, over cap.
    with pytest.raises(StackCapExceededError):
        cube_up_single(sh, "r01", pairs=10)


# --------------------------------------------------------------------------- #
#  Section C: cube_up_bulk
# --------------------------------------------------------------------------- #


def test_C1_bulk_cascades():
    """Bulk mode propagates pairs upward across tiers within one call."""
    from d2rr_toolkit.operations.rune_cube_up import (
        count_runes_in_section5,
        cube_up_bulk,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(_TC61).parse()
    pre = count_runes_in_section5(sh)
    # TC61: r01=9 -> 4 pairs -> 4 r02 -> 2 pairs -> 2 r03 -> 1 pair -> 1 r04
    res = cube_up_bulk(sh)
    post = count_runes_in_section5(sh)

    # r01 input path
    assert res.removed.get("r01", 0) == pre["r01"] - (pre["r01"] % 2)
    # Cascade signature: r02 and r03 both appear in removed AND added (cascaded)
    assert "r02" in res.added
    assert "r02" in res.removed  # r02 was produced then consumed by cascade
    assert "r03" in res.added
    # Cleanup: the only runes that survive are the odd ones (leftovers)
    assert post.get("r01", 0) == pre["r01"] % 2


def test_C2_bulk_respects_min_keep():
    """min_keep floor is enforced per rune code."""
    from d2rr_toolkit.operations.rune_cube_up import (
        count_runes_in_section5,
        cube_up_bulk,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(_TC61).parse()
    pre = count_runes_in_section5(sh)
    r09_pre = pre.get("r09", 0)
    assert r09_pre >= 3

    res = cube_up_bulk(sh, min_keep={"r09": r09_pre})  # keep all r09
    post = count_runes_in_section5(sh)

    assert post.get("r09", 0) >= r09_pre, "min_keep floor violated"
    assert "r09" not in res.removed or res.removed["r09"] == 0


def test_C3_bulk_caps_instead_of_raising(tmp_stash: Path):
    """Overflow is silently capped in bulk mode and reported in result."""
    from d2rr_toolkit.operations.rune_cube_up import (
        cube_up_bulk,
        _synthesize_rune_parsed_item,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.item_utils import clone_with_quantity

    sh = D2IParser(_TC61).parse()
    tab5 = sh.tabs[5]
    # Set up a case where r01 has lots of runes and r02 is near cap.
    r01_items = [it for it in tab5.items if it.item_code == "r01"]
    if r01_items:
        idx = tab5.items.index(r01_items[0])
        tab5.items[idx] = clone_with_quantity(r01_items[0], 99)
    tab5.items.append(_synthesize_rune_parsed_item("r02", display_quantity=98))
    # Pre-condition: r01=99, r02=98. Bulk: 49 pairs of r01 should produce 49 r02
    # but cap leaves room for only 1 more, so 48 capped.
    res = cube_up_bulk(sh)
    assert "r02" in res.capped_by_output_limit
    assert res.capped_by_output_limit["r02"] >= 1


# --------------------------------------------------------------------------- #
#  Section D: File-level integration
# --------------------------------------------------------------------------- #


def test_D1_file_single_produces_valid_d2i(tmp_stash: Path):
    """End-to-end: cube_up_file_single -> parseable output file."""
    from d2rr_toolkit.operations.rune_cube_up import (
        count_runes_in_section5,
        cube_up_file_single,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    pre = count_runes_in_section5(D2IParser(tmp_stash).parse())
    res = cube_up_file_single(tmp_stash, "r01", pairs=2, backup=False)
    post = count_runes_in_section5(D2IParser(tmp_stash).parse())

    assert res.output_path == tmp_stash
    assert res.backup_path is None
    assert post.get("r01", 0) == pre["r01"] - 4
    assert post.get("r02", 0) == 2
    # Signature check on the written file
    buf = tmp_stash.read_bytes()
    assert buf[:4] == b"\x55\xaa\x55\xaa", "D2I magic header missing after write"


def test_D2_file_single_creates_backup(tmp_stash: Path):
    """Backup is created when writing in-place (default)."""
    from d2rr_toolkit.operations.rune_cube_up import cube_up_file_single

    res = cube_up_file_single(tmp_stash, "r01", pairs=1, backup=True)
    assert res.backup_path is not None
    assert res.backup_path.exists(), "backup file does not exist"
    # The backup contents should equal the pre-cube source (i.e. original TC61).
    assert res.backup_path.read_bytes() == _TC61.read_bytes()


def test_D2b_file_no_backup_when_out_set(tmp_stash: Path, tmp_path: Path):
    """Passing --out skips the backup."""
    from d2rr_toolkit.operations.rune_cube_up import cube_up_file_single

    out = tmp_path / "result.d2i"
    res = cube_up_file_single(tmp_stash, "r01", pairs=1, dest_path=out, backup=True)
    assert res.backup_path is None
    assert out.exists()


def test_D3_output_splice_roundtrips_byte_exact(tmp_stash: Path):
    """After cube-up, the file must survive a forced-splice roundtrip byte-exact."""
    from d2rr_toolkit.operations.rune_cube_up import cube_up_file_single
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    cube_up_file_single(tmp_stash, "r01", pairs=2, backup=False)
    src_bytes = tmp_stash.read_bytes()
    sh = D2IParser(tmp_stash).parse()

    writer = D2IWriter.from_stash(src_bytes, sh)
    # Force splice on tab 5 by pop-and-reinsert.
    first = writer._tab_items[5].pop(0)
    writer._tab_items[5].insert(0, first)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "rt.d2i"
        writer.write(out)
        dst_bytes = out.read_bytes()
    assert dst_bytes == src_bytes, (
        "forced-splice roundtrip diverged from cube-up output - "
        "our writer cannot preserve synthesized items byte-exact"
    )


def test_D4_cli_rune_subcommand(tmp_stash: Path):
    """CLI ``cube-up rune`` exits 0 and renders a summary table."""
    from typer.testing import CliRunner

    from d2rr_toolkit.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "cube-up",
            "rune",
            str(tmp_stash),
            "--rune",
            "r01",
            "--pairs",
            "2",
            "--no-backup",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "r01" in result.stdout
    assert "r02" in result.stdout


def test_D5_cli_bulk_subcommand(tmp_stash: Path):
    """CLI ``cube-up bulk`` exits 0 and respects --keep."""
    from typer.testing import CliRunner

    from d2rr_toolkit.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "cube-up",
            "bulk",
            str(tmp_stash),
            "--keep",
            "r09:3",
            "--no-backup",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Cascading" in result.stdout


def test_D6_cli_bulk_invalid_keep_format():
    """--keep with bad syntax fails cleanly (BadParameter)."""
    from typer.testing import CliRunner

    from d2rr_toolkit.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["cube-up", "bulk", "dummy.d2i", "--keep", "bogus", "--no-backup"],
    )
    # Typer.BadParameter surfaces as exit code 2
    assert result.exit_code != 0
