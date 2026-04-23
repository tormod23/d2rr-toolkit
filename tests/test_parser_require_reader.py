"""D2SParser._require_reader raises RuntimeError on None.

Previously the code used ``assert self._reader is not None`` which is
stripped under ``python -O``. The helper must raise a diagnosable
RuntimeError instead, even with asserts stripped.
"""

from __future__ import annotations

import pytest

from d2rr_toolkit.parsers.d2s_parser import D2SParser


def test_require_reader_raises_when_not_primed() -> None:
    parser = D2SParser.__new__(D2SParser)
    parser._reader = None  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="reader not initialised"):
        parser._require_reader()


def test_require_reader_returns_reader_when_primed() -> None:
    class _Stub:
        pass

    parser = D2SParser.__new__(D2SParser)
    stub = _Stub()
    parser._reader = stub  # type: ignore[attr-defined]
    assert parser._require_reader() is stub
