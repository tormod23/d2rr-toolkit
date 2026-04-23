"""Parser-layer exception types.

Lives in its own module to avoid the circular-import deadlock between
:mod:`d2rr_toolkit.parsers.d2s_parser` (which defines the public parser
entry points) and :mod:`d2rr_toolkit.parsers.d2s_parser_items` (which is
imported by ``d2s_parser`` at its module tail and therefore cannot
import back from it at module-top level).

Any new parser-layer exception types belong here too.
"""

from __future__ import annotations


class GameDataNotLoadedError(RuntimeError):
    """Raised when the parser is invoked before game-data singletons are populated.

    The item-parsing pipeline depends on ItemTypeDatabase, ItemStatCostDatabase,
    and SkillDatabase singletons. When any of them is empty, :meth:`classify`
    silently returns ``UNKNOWN`` and the parser degrades to a speculative
    "skip to terminator" branch that produces bit-misaligned output - valid
    item codes get decoded, then "Unknown stat_id=506" (impossible, >435 max)
    cascades into false items, catastrophic item loss (observed: 5/57 items
    on real SharedStash files). The only safe default is to fail-loud.

    Real-world impact: silently writing 91% wrong data to the archive DB.
    Fix: call :func:`load_item_types`, :func:`load_item_stat_cost`,
    :func:`load_skills` before parsing - or let the parser auto-load
    (which it now does; this error fires only when auto-load is disabled
    or itself fails).
    """

