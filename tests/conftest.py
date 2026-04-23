"""Shared pytest configuration.

Registers custom markers and provides helpers that let tests
voluntarily skip when running in environments that lack the local
D2R + Reimagined install (e.g. GitHub Actions CI).
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so they don't raise PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "needs_game_data: requires a local D2R Reimagined install + CASC "
        'archive to run (skipped by CI via `-m "not needs_game_data"`)',
    )
    config.addinivalue_line(
        "markers",
        "needs_live_stash: requires the user's current SharedStash save "
        "file under the D2RR save dir "
        "(~/Saved Games/Diablo II Resurrected/mods/ReimaginedThree/), "
        "not the base-game D2R save dir",
    )
