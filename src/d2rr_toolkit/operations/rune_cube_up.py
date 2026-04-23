"""Reimagined rune cube-up operation for Section 5 of the shared stash.

## What this does

Reimagined exposes a cube recipe that transmutes 2 runes of the same
tier into 1 rune of the next tier (up to Zod, r33). This module
exposes that recipe as a bulk operation on a parsed ``.d2i`` tree so
users can cube hundreds of low runes into a handful of high runes in
one shot, without going through the in-game cube UI one pair at a
time.

Two public entry points:

  * :func:`cube_up_single` - upgrade a specific number of *pairs* of
    one rune code. Intended for a future "slider" GUI or one-shot
    scripting.

  * :func:`cube_up_bulk` - cascading upgrade across r01..r32 in a
    single pass, with per-rune minimum-keep thresholds. An r15 that
    gets upgraded to r16 is visible to the r16 iteration, so the chain
    naturally cascades upward.

Both operate on the ``ParsedSharedStash`` tree produced by
:class:`d2rr_toolkit.parsers.d2i_parser.D2IParser`. Callers are
responsible for creating a backup via
:func:`d2rr_toolkit.backup.create_backup` and for serialising the
modified stash back to disk via
:class:`d2rr_toolkit.writers.d2i_writer.D2IWriter`.

## Invariants

  * Only classic runes ``r01..r33`` (simple items) are touched. Stacked
    runes (``s##``, the Reimagined "Rune Stack" type) are ignored;
    per the archive policy they never appear in Section 5 anyway.
  * All work happens in tab index 5 (``stash.tabs[5]``), the base-game
    "Gems / Materials / Runes" combined tab.
  * Stack-size bounds follow
    ``item_utils.SECTION5_MIN_QUANTITY..SECTION5_MAX_QUANTITY`` (1..99).
    Exceeding 99 by cubing will cap the consumed pairs to what fits in
    the output stack and raise :class:`StackCapExceededError` for
    :func:`cube_up_single`; the bulk path silently caps.
  * Trying to upgrade r33 raises :class:`CannotUpgradeMaxRuneError` -
    the GUI should refuse to offer this as an option (user directive).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from d2rr_toolkit.writers.item_utils import (
    SECTION5_MAX_QUANTITY,
    SECTION5_MIN_QUANTITY,
    clone_with_quantity,
    synthesize_simple_item_blob,
)

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedItem
    from d2rr_toolkit.parsers.d2i_parser import ParsedSharedStash

logger = logging.getLogger(__name__)


SECTION5_TAB_INDEX = 5
"""Index of the 'Gems / Materials / Runes' tab in a D2RR shared stash."""

_RUNE_CODE_RE = re.compile(r"^r(0[1-9]|[12][0-9]|3[0-3])$")


# ── Exceptions ───────────────────────────────────────────────────────────────


class RuneUpgradeError(Exception):
    """Base class for cube-up failures."""


class InvalidRuneCodeError(RuneUpgradeError, ValueError):
    """Raised when a code is not a classic rune r01..r33."""


class CannotUpgradeMaxRuneError(RuneUpgradeError):
    """Raised when the caller tries to upgrade r33 (Zod)."""


class NotEnoughRunesError(RuneUpgradeError):
    """Raised when the caller requests more pairs than are available."""


class StackCapExceededError(RuneUpgradeError):
    """Raised when the cube-up would push the output stack beyond 99."""


class Section5MissingError(RuneUpgradeError):
    """Raised when the stash has no Section 5 tab (malformed input)."""


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class CubeUpResult:
    """Summary of a cube-up run, for display / logging / CLI output.

    ``removed`` and ``added`` are expressed in *runes* (display
    quantity), not items. E.g. ``removed={'r01': 20}`` means the
    operation consumed 20 r01 across however many stacks held them.
    """

    removed: dict[str, int] = field(default_factory=dict)
    added: dict[str, int] = field(default_factory=dict)
    remaining: dict[str, int] = field(default_factory=dict)
    capped_by_output_limit: dict[str, int] = field(default_factory=dict)
    """For each output rune code whose stack was limited by the 99-cap,
    the number of pairs that could NOT be produced. Bulk mode only."""


# ── Rune helpers --------------------------------------------------------------


def _validate_rune_code(code: str) -> str:
    """Normalise and validate a rune code string."""
    normalised = (code or "").strip().lower()
    if not _RUNE_CODE_RE.match(normalised):
        raise InvalidRuneCodeError(
            f"Not a classic rune code: {code!r}. Expected r01..r33."
        )
    return normalised


def _next_rune_code(code: str) -> str:
    """Return the next-tier rune code (r01 -> r02, r32 -> r33).

    Raises :class:`CannotUpgradeMaxRuneError` when called on r33.
    """
    code = _validate_rune_code(code)
    n = int(code[1:])
    if n >= 33:
        raise CannotUpgradeMaxRuneError(
            f"{code} is the highest-tier rune and cannot be cubed up further."
        )
    return f"r{n + 1:02d}"


def _section5_tab(stash: "ParsedSharedStash"):
    """Return the Section 5 tab or raise if missing."""
    if len(stash.tabs) <= SECTION5_TAB_INDEX:
        raise Section5MissingError(
            f"Stash has only {len(stash.tabs)} tabs; Section 5 (index "
            f"{SECTION5_TAB_INDEX}) is missing - this is likely a malformed "
            f".d2i or an older format without Section 5."
        )
    return stash.tabs[SECTION5_TAB_INDEX]


def count_runes_in_section5(stash: "ParsedSharedStash") -> dict[str, int]:
    """Return {rune_code: total display_quantity} for all r## stacks in Section 5.

    Counts the display (user-visible) stack sizes, summed per rune
    code. Stacked runes (s##) are intentionally excluded - they never
    appear in a properly-archived Section 5 per the toolkit's archive
    policy. Non-rune items in Section 5 are ignored.
    """
    tab = _section5_tab(stash)
    counts: dict[str, int] = {}
    for item in tab.items:
        code = (item.item_code or "").lower()
        if _RUNE_CODE_RE.match(code):
            counts[code] = counts.get(code, 0) + item.display_quantity
    return counts


def _find_rune_items(tab, code: str) -> list["ParsedItem"]:
    """Return all ParsedItem entries in ``tab.items`` matching ``code``."""
    return [it for it in tab.items if (it.item_code or "").lower() == code]


# ── Mutation primitives ------------------------------------------------------


def _remove_runes(tab, code: str, amount: int) -> None:
    """Remove ``amount`` runes of ``code`` from Section 5 (by display count).

    Walks existing stacks in list order, reducing the top-most stack's
    ``display_quantity`` first. When a stack reaches quantity=0 it is
    removed from ``tab.items`` entirely (zombie entries are forbidden;
    see ``SECTION5_MIN_QUANTITY`` in :mod:`writers.item_utils`).

    Assumes the caller already verified ``sum(display_quantity) >= amount``.
    """
    remaining = amount
    # Iterate over a snapshot so we can remove items cleanly while looping.
    for item in list(tab.items):
        if remaining <= 0:
            break
        if (item.item_code or "").lower() != code:
            continue
        current = item.display_quantity
        if current <= remaining:
            # Consume the whole stack - drop it from the list.
            tab.items.remove(item)
            remaining -= current
        else:
            # Partially consume - shrink the stack via clone_with_quantity
            # so source_data stays bit-accurate.
            new_item = clone_with_quantity(item, current - remaining)
            idx = tab.items.index(item)
            tab.items[idx] = new_item
            remaining = 0
    if remaining > 0:
        # Defensive: caller should have validated counts upstream.
        raise NotEnoughRunesError(
            f"Wanted to remove {amount} {code}, short by {remaining}."
        )


def _add_runes(tab, code: str, amount: int) -> None:
    """Add ``amount`` runes of ``code`` to Section 5.

    If a stack of ``code`` already exists, its display_quantity is
    bumped (capped at 99; excess raises :class:`StackCapExceededError`).
    Otherwise a new ``ParsedItem`` is synthesized and appended to the
    tab's item list.
    """
    existing = _find_rune_items(tab, code)
    if existing:
        # Section 5 forbids duplicate stacks per code (parser / writer
        # invariant). Bump the only stack.
        stack = existing[0]
        new_total = stack.display_quantity + amount
        if new_total > SECTION5_MAX_QUANTITY:
            raise StackCapExceededError(
                f"Adding {amount} {code} would push stack to {new_total}, "
                f"over the {SECTION5_MAX_QUANTITY}-rune cap."
            )
        idx = tab.items.index(stack)
        tab.items[idx] = clone_with_quantity(stack, new_total)
    else:
        if amount > SECTION5_MAX_QUANTITY:
            raise StackCapExceededError(
                f"Cannot synthesize a new {code} stack of {amount} - "
                f"exceeds the {SECTION5_MAX_QUANTITY}-rune cap."
            )
        new_item = _synthesize_rune_parsed_item(code, display_quantity=amount)
        tab.items.append(new_item)


def _synthesize_rune_parsed_item(code: str, *, display_quantity: int) -> "ParsedItem":
    """Construct a brand-new ``ParsedItem`` for a rune stack.

    The ``source_data`` blob is synthesized by
    :func:`synthesize_simple_item_blob`; all ``ParsedItem`` metadata
    (flags, quantity_bit_offset, quantity_bit_width) is populated
    consistently with what the parser would record for the same item.

    Position (x/y) is fixed to (0, 0). Section 5 has no user-visible
    grid so position doesn't affect rendering; TC67/TC61 templates
    already show multiple items sharing (0, 0).
    """
    from d2rr_toolkit.constants import ITEM_BIT_HUFFMAN_START
    from d2rr_toolkit.models.character import ItemFlags, ParsedItem
    from d2rr_toolkit.writers.item_utils import encode_huffman_code

    code = _validate_rune_code(code)
    blob = synthesize_simple_item_blob(
        code,
        display_quantity=display_quantity,
        is_quantity_item=True,  # all r## are quantity_item=1 in Reimagined
        position_x=0,
        position_y=0,
        panel_id=5,
        location_id=0,
        equipped_slot=0,
        identified=True,
    )
    # quantity_bit_offset = bit position AFTER Huffman + 1 socket bit.
    huff_len = len(encode_huffman_code(code))
    qty_offset = ITEM_BIT_HUFFMAN_START + huff_len + 1  # item-relative bit pos
    raw_quantity = (display_quantity << 1) | 1

    flags = ItemFlags(
        identified=True,
        socketed=False,
        starter_item=False,
        simple=True,
        ethereal=False,
        personalized=False,
        runeword=False,
        location_id=0,
        equipped_slot=0,
        position_x=0,
        position_y=0,
        panel_id=5,
    )
    return ParsedItem(
        item_code=code,
        flags=flags,
        source_data=blob,
        quantity=raw_quantity,
        quantity_bit_offset=qty_offset,
        quantity_bit_width=9,
    )


# ── Public API: single ------------------------------------------------------


def cube_up_single(
    stash: "ParsedSharedStash",
    rune_code: str,
    pairs: int,
) -> CubeUpResult:
    """Upgrade ``pairs`` pairs of ``rune_code`` into the next-tier rune.

    Each pair consumes 2 input runes and produces 1 output rune.
    For example ``cube_up_single(stash, 'r01', 10)`` consumes 20 r01
    and produces 10 r02.

    Args:
        stash:     Parsed shared stash (mutated in place).
        rune_code: Input rune code, r01..r32.
        pairs:     Number of pairs to transmute. Must be >= 1.

    Returns:
        :class:`CubeUpResult` with the per-rune deltas.

    Raises:
        InvalidRuneCodeError:      ``rune_code`` is not r01..r33.
        CannotUpgradeMaxRuneError: ``rune_code`` is r33.
        NotEnoughRunesError:       Section 5 doesn't hold ``2 * pairs``
                                    of ``rune_code``.
        StackCapExceededError:     Output stack would exceed 99.
        Section5MissingError:      Stash has no Section 5 tab.
    """
    if pairs < 1:
        raise ValueError(f"pairs must be >= 1, got {pairs}")

    code = _validate_rune_code(rune_code)
    next_code = _next_rune_code(code)
    tab = _section5_tab(stash)

    counts = count_runes_in_section5(stash)
    available = counts.get(code, 0)
    consume = pairs * 2
    if available < consume:
        raise NotEnoughRunesError(
            f"Cube-up needs {consume} {code}, only {available} available in Section 5."
        )

    # Check output cap BEFORE mutating so we fail early.
    next_existing = counts.get(next_code, 0)
    if next_existing + pairs > SECTION5_MAX_QUANTITY:
        excess = next_existing + pairs - SECTION5_MAX_QUANTITY
        raise StackCapExceededError(
            f"Producing {pairs} {next_code} would push the stack to "
            f"{next_existing + pairs}, {excess} over the "
            f"{SECTION5_MAX_QUANTITY}-rune cap. Reduce the request "
            f"by {excess} pair(s)."
        )

    _remove_runes(tab, code, consume)
    _add_runes(tab, next_code, pairs)

    # Recount for accurate "remaining" view.
    final = count_runes_in_section5(stash)
    return CubeUpResult(
        removed={code: consume},
        added={next_code: pairs},
        remaining={code: final.get(code, 0), next_code: final.get(next_code, 0)},
    )


# ── Public API: bulk --------------------------------------------------------


def cube_up_bulk(
    stash: "ParsedSharedStash",
    min_keep: dict[str, int] | None = None,
) -> CubeUpResult:
    """Cascading cube-up across r01..r32 in a single pass.

    For each rune tier in ascending order, compute how many pairs can
    be upgraded (respecting the per-rune ``min_keep`` threshold and
    the 99-rune output cap) and perform the upgrade. Because results
    accumulate upward, runes produced at tier N are visible to the
    tier-N iteration that follows.

    This is a "do as much as possible" sweep - unlike
    :func:`cube_up_single`, a cap hit on the output stack does NOT
    raise; pairs that would overflow are reported in
    ``result.capped_by_output_limit``.

    Args:
        stash:    Parsed shared stash (mutated in place).
        min_keep: Optional per-rune-code floor. For each code present,
                  at least ``min_keep[code]`` runes are left untouched.
                  Unlisted codes default to a floor of 0.

    Returns:
        :class:`CubeUpResult` aggregating every tier's contribution.
    """
    min_keep = dict(min_keep or {})
    # Normalise keys so the caller's casing doesn't matter.
    min_keep = {_validate_rune_code(k): max(0, int(v)) for k, v in min_keep.items()}
    tab = _section5_tab(stash)

    result = CubeUpResult()

    for level in range(1, 33):  # r01..r32 upgrade into r02..r33
        code = f"r{level:02d}"
        next_code = f"r{level + 1:02d}"
        counts = count_runes_in_section5(stash)
        current = counts.get(code, 0)
        keep = min_keep.get(code, 0)
        upgradable = max(0, current - keep)
        pairs_wanted = upgradable // 2
        if pairs_wanted <= 0:
            continue

        # Respect the 99-rune cap on the output stack.
        next_existing = counts.get(next_code, 0)
        pairs_capped = max(0, SECTION5_MAX_QUANTITY - next_existing)
        pairs = min(pairs_wanted, pairs_capped)
        overflow = pairs_wanted - pairs
        if overflow > 0:
            result.capped_by_output_limit[next_code] = (
                result.capped_by_output_limit.get(next_code, 0) + overflow
            )

        if pairs == 0:
            continue

        _remove_runes(tab, code, pairs * 2)
        _add_runes(tab, next_code, pairs)
        result.removed[code] = result.removed.get(code, 0) + pairs * 2
        result.added[next_code] = result.added.get(next_code, 0) + pairs
        logger.info(
            "cube_up_bulk: %d %s -> %d %s (kept %d, capped %d)",
            pairs * 2, code, pairs, next_code, keep, overflow,
        )

    result.remaining = count_runes_in_section5(stash)
    return result


# ── End-to-end file orchestration -------------------------------------------


@dataclass
class CubeUpFileResult:
    """Summary returned by :func:`cube_up_file_single` / :func:`cube_up_file_bulk`.

    Extends :class:`CubeUpResult` with the paths of the source and the
    backup so callers can report both to the user (and the CLI can show
    the rollback path if anything looks off).
    """

    result: CubeUpResult
    source_path: Path
    backup_path: Path | None
    output_path: Path


def _execute_cube_up_file(
    src_path: Path,
    mutator,
    *,
    dest_path: Path | None = None,
    backup: bool = True,
) -> CubeUpFileResult:
    """Shared parse -> backup -> mutate -> write pipeline for cube-up.

    Mutation ordering is the tricky part: ``D2IWriter.from_stash``
    captures BOTH the "current" and "original" item lists at call
    time, so any mutation performed before that snapshot becomes
    invisible to the writer. We therefore (a) snapshot the original
    item lists here, (b) apply the mutation, and (c) construct the
    writer explicitly with the pre-mutation snapshot so its splice
    path sees the delta and rewrites the section. [BV by tests]

    ``mutator`` is a callable that takes the parsed ``stash`` and
    returns a :class:`CubeUpResult`. It is free to mutate
    ``stash.tabs[5].items`` in place.
    """
    from d2rr_toolkit.backup import create_backup
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    src_path = Path(src_path)
    dest = Path(dest_path) if dest_path is not None else src_path

    src_bytes = src_path.read_bytes()
    stash = D2IParser(src_path).parse()

    # Snapshot BEFORE mutation so the writer can detect the delta.
    pre_mutation_items = [list(tab.items) for tab in stash.tabs]

    result = mutator(stash)

    backup_path: Path | None = None
    # Only backup when we're overwriting the source file.
    if backup and dest.resolve() == src_path.resolve():
        backup_path = create_backup(src_path)

    # Build the writer manually with explicit pre/post lists so the
    # splice path fires on the tabs we actually modified.
    post_mutation_items = [list(tab.items) for tab in stash.tabs]
    writer = D2IWriter(src_bytes, post_mutation_items, _original_items=pre_mutation_items)
    writer.write(dest)

    return CubeUpFileResult(
        result=result,
        source_path=src_path,
        backup_path=backup_path,
        output_path=dest,
    )


def cube_up_file_single(
    src_path: Path,
    rune_code: str,
    pairs: int,
    *,
    dest_path: Path | None = None,
    backup: bool = True,
) -> CubeUpFileResult:
    """End-to-end single-rune cube-up on a .d2i file.

    Parses ``src_path``, (optionally) backs it up, runs
    :func:`cube_up_single` on the parsed stash, and writes the result
    to ``dest_path`` (defaults to ``src_path``, i.e. in-place).

    Args:
        src_path:  Path to the source ``.d2i`` file.
        rune_code: Rune to upgrade, r01..r32.
        pairs:     Number of pairs to cube up.
        dest_path: Where to write the result (defaults to ``src_path``).
        backup:    When True (default) and ``dest_path == src_path``,
                   create a timestamped backup via
                   :func:`d2rr_toolkit.backup.create_backup` before
                   overwriting.

    Returns:
        :class:`CubeUpFileResult` with the summary, backup path, and
        output path.
    """
    def _do(stash):
        return cube_up_single(stash, rune_code, pairs)

    return _execute_cube_up_file(src_path, _do, dest_path=dest_path, backup=backup)


def cube_up_file_bulk(
    src_path: Path,
    *,
    min_keep: dict[str, int] | None = None,
    dest_path: Path | None = None,
    backup: bool = True,
) -> CubeUpFileResult:
    """End-to-end cascading cube-up on a .d2i file.

    See :func:`cube_up_bulk` for the cascading semantics.

    Args:
        src_path:  Path to the source ``.d2i`` file.
        min_keep:  Optional per-rune floor (see :func:`cube_up_bulk`).
        dest_path: Where to write the result (defaults to ``src_path``).
        backup:    When True and writing in-place, create a backup first.

    Returns:
        :class:`CubeUpFileResult`.
    """
    def _do(stash):
        return cube_up_bulk(stash, min_keep=min_keep)

    return _execute_cube_up_file(src_path, _do, dest_path=dest_path, backup=backup)


# ── Synthesizer self-test (runs on import) ----------------------------------


_SELF_TEST_DONE = False


def _self_test() -> None:
    """Verify the simple-item synthesizer against a known-good r01 template.

    The template is a 9-rune El stack positioned at (2, 0) in TC61's
    Section 5 - a byte sequence taken directly from a game-written
    shared stash. If our synthesizer's output ever diverges (e.g. via
    a regression in the Huffman encoder or the flag-bit layout), this
    self-test raises at import time so the bug is loud instead of
    latent.

    The test exercises the full synthesis path end-to-end: Huffman
    encoding, header flag placement, position fields, panel=5, and
    the 9-bit quantity field including the bit-0 alignment flag.
    """
    global _SELF_TEST_DONE
    if _SELF_TEST_DONE:
        return
    # r01 @ (2, 0) stash, display_quantity=9
    # Taken from TC61/MixedSection5.d2i ground-truth.
    expected = bytes.fromhex("10 00 a0 00 05 08 f4 7c 7f 32 01".replace(" ", ""))
    synth = synthesize_simple_item_blob(
        "r01",
        display_quantity=9,
        is_quantity_item=True,
        position_x=2,
        position_y=0,
        panel_id=5,
        location_id=0,
        equipped_slot=0,
        identified=True,
    )
    if synth != expected:
        raise RuntimeError(
            "Rune synthesizer self-test failed: byte output diverged from "
            "the TC61 r01 template. This indicates a regression in "
            "Huffman encoding, flag-bit placement, or the 9-bit quantity "
            "encoding. Expected %s, got %s." % (expected.hex(), synth.hex())
        )
    _SELF_TEST_DONE = True


_self_test()
