"""d2rr-toolkit -- D2R Reimagined Domain Library.

Provides models, parsers, writers, game data loaders, display logic,
sprite resolution, palette-based tinting, and database operations for
Diablo II Resurrected (Reimagined mod).

Usage::

    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.game_data.item_types import load_item_types, get_item_type_db

    character = D2SParser(Path("char.d2s")).parse()

## Logging

``d2rr_toolkit`` is **silent by default**. It follows the Python
standard library-logging convention: the top-level logger has a
``NullHandler`` attached and ``propagate = False``, so no records
reach the root logger or stderr unless the consumer explicitly
opts in.

To see toolkit logs in your application::

    from d2rr_toolkit.logging import enable_logging
    import logging

    enable_logging()                    # INFO and above
    enable_logging(level=logging.DEBUG) # everything

Equivalently, the standard ``logging`` API works::

    import logging
    logging.getLogger("d2rr_toolkit").setLevel(logging.INFO)
    logging.getLogger("d2rr_toolkit").propagate = True

The DEBUG channel is intentionally verbose (parser bit-stream
operations, palette/colormap loads, sprite resolution steps).
Enable it only when you need to debug a specific issue - running
with DEBUG in production can produce thousands of records per
second for a full ``D2SParser.parse()`` call.
"""

# Library logging hygiene - see docstring above.
# Must be at module import time, before any submodule can log.
import logging as _logging

_logging.getLogger(__name__).addHandler(_logging.NullHandler())
# propagate=False stops the consumer's root-logger handlers from seeing
# toolkit records, unless opted in via d2rr_toolkit.logging.enable_logging().
_logging.getLogger(__name__).propagate = False

del _logging
