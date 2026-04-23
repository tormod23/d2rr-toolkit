"""Post-retry validation of the Rare-MISC 7-slot QSD retry path.

The retry is already exercised end-to-end by the TC24 snapshot fixture
(`tests/cases/TC24/`), which pins the happy-path outcome byte-for-byte.
These tests add direct unit coverage of the new
``_validate_rare_misc_7slot_retry`` helper so the overshoot / buffer-
past-end failure modes can be asserted in isolation -- crafting a
malformed D2S byte sequence that drives the retry into a specific bad
state is fragile and better left to the snapshot gate for happy path.
"""

from __future__ import annotations

import pytest

from d2rr_toolkit.exceptions import SpecVerificationError
from d2rr_toolkit.parsers.d2s_parser import D2SParser


class _FakeReader:
    def __init__(self, bit_pos: int, buffer_bytes: int = 1024) -> None:
        self.bit_pos = bit_pos
        self._data = b"\x00" * buffer_bytes


def _make_parser() -> D2SParser:
    parser = object.__new__(D2SParser)
    parser._section_end_byte = None  # type: ignore[attr-defined]
    parser._reader = None  # type: ignore[attr-defined]
    return parser


def test_retry_validation_passes_within_section() -> None:
    parser = _make_parser()
    parser._section_end_byte = 200  # type: ignore[attr-defined]
    parser._reader = _FakeReader(bit_pos=100 * 8)  # type: ignore[attr-defined]
    # Must not raise.
    parser._validate_rare_misc_7slot_retry(
        item_start_bit=50 * 8,
        code="jew",
        quality=6,
    )


def test_retry_validation_rejects_section_overshoot() -> None:
    parser = _make_parser()
    parser._section_end_byte = 100  # type: ignore[attr-defined]
    parser._reader = _FakeReader(bit_pos=150 * 8)  # type: ignore[attr-defined]
    with pytest.raises(SpecVerificationError) as excinfo:
        parser._validate_rare_misc_7slot_retry(
            item_start_bit=50 * 8,
            code="jew",
            quality=6,
        )
    assert "rare_misc_7slot_retry" in excinfo.value.field
    assert "overshoot" in str(excinfo.value).lower()


def test_retry_validation_rejects_buffer_overrun() -> None:
    parser = _make_parser()
    # Section boundary not set; buffer is only 100 bytes but reader is at 150.
    parser._reader = _FakeReader(bit_pos=150 * 8, buffer_bytes=100)  # type: ignore[attr-defined]
    with pytest.raises(SpecVerificationError) as excinfo:
        parser._validate_rare_misc_7slot_retry(
            item_start_bit=10 * 8,
            code="jew",
            quality=8,
        )
    assert excinfo.value.field == "rare_misc_7slot_retry"


def test_retry_validation_no_section_bound_allows_sane_position() -> None:
    parser = _make_parser()
    parser._reader = _FakeReader(bit_pos=50 * 8, buffer_bytes=100)  # type: ignore[attr-defined]
    parser._validate_rare_misc_7slot_retry(
        item_start_bit=10 * 8,
        code="cm1",
        quality=6,
    )
