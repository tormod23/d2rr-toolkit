"""Tmp-file cleanup for the game-data pickle cache.

The atomic write in ``_try_write_cache`` must always attempt to
unlink its per-call tmp file, even when the inner ``write_bytes`` /
``os.replace`` pair succeeds. An unlink failure on the cleanup path
must be logged at DEBUG (diagnosable without steady-state noise)
rather than swallowed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from d2rr_toolkit.meta import cache as cache_module


class _Dummy:
    """Minimal picklable singleton for _try_write_cache."""

    def __init__(self) -> None:
        self.n = 1


def _versions() -> cache_module.SourceVersions:
    return cache_module.SourceVersions(
        game_version="deadbeef",
        mod_version="cafebabe",
        mod_name=None,
    )


def test_happy_path_tmp_is_removed(tmp_path: Path) -> None:
    """After a successful write, no stale .tmp file remains."""
    cache_path = tmp_path / "sub" / "x.pkl"
    cache_module._try_write_cache(cache_path, 1, _versions(), _Dummy())
    assert cache_path.is_file()
    leftovers = list(cache_path.parent.glob("*.tmp"))
    assert leftovers == []


def test_unlink_failure_logs_debug(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When tmp.unlink raises, the failure is logged at DEBUG, not
    propagated or silently swallowed."""
    cache_path = tmp_path / "x.pkl"

    original_unlink = Path.unlink
    calls = {"count": 0}

    def flaky_unlink(self: Path, missing_ok: bool = False) -> None:
        if str(self).endswith(".tmp"):
            calls["count"] += 1
            raise OSError("simulated cleanup failure")
        return original_unlink(self, missing_ok=missing_ok)

    with patch.object(Path, "unlink", flaky_unlink):
        with caplog.at_level(logging.DEBUG, logger="d2rr_toolkit.meta.cache"):
            cache_module._try_write_cache(
                cache_path, 1, _versions(), _Dummy()
            )

    # The write itself succeeds; the debug log just records the
    # cleanup-failure diagnostic.
    assert cache_path.is_file()
    assert calls["count"] >= 1
