"""Optional logging utilities for d2rr_toolkit consumers.

By default the toolkit is silent. The top-level ``d2rr_toolkit`` logger
has a ``NullHandler`` attached and ``propagate = False``, so records
never reach the consumer's root logger or stderr.

Consumers that want to see toolkit logs can enable them via one of
the two equivalent methods:

1. The convenience functions in this module (recommended)::

    from d2rr_toolkit.logging import enable_logging
    import logging

    enable_logging()                    # INFO and above
    enable_logging(level=logging.DEBUG) # everything

2. The standard library API::

    import logging
    log = logging.getLogger("d2rr_toolkit")
    log.setLevel(logging.INFO)
    log.propagate = True

The two approaches produce the same result. The convenience functions
are purely a documented verb - they hold no hidden state.

Note on the module name
-----------------------

This module shadows the stdlib ``logging`` module within the
``d2rr_toolkit`` namespace. It does **not** prevent other toolkit
modules from using the stdlib ``logging`` module: Python 3 resolves
``import logging`` as an absolute import against ``sys.path``, not
against the current package. Submodules therefore see the real
stdlib ``logging``, not this one. To use this module from within
the toolkit itself, always import it explicitly::

    from d2rr_toolkit.logging import enable_logging
"""

from __future__ import annotations

import logging as _logging

__all__ = ["enable_logging", "disable_logging"]


_TOOLKIT_LOGGER_NAME = "d2rr_toolkit"


def enable_logging(
    level: int = _logging.INFO,
    *,
    propagate: bool = True,
) -> None:
    """Enable d2rr_toolkit logging at ``level`` or above.

    After this call, toolkit records at ``level`` or higher propagate
    to the consumer's root-logger handlers (unless ``propagate=False``).

    Args:
        level:     Minimum severity to emit. Defaults to ``logging.INFO``
                   so that verbose DEBUG output stays opt-in-opt-in.
                   Use ``logging.DEBUG`` to see everything.
        propagate: If ``True`` (default), records reach the consumer's
                   root-logger handlers through standard propagation.
                   If ``False``, the toolkit keeps its own handler chain
                   (only relevant when the consumer attaches a handler
                   directly to the ``d2rr_toolkit`` logger).
    """
    log = _logging.getLogger(_TOOLKIT_LOGGER_NAME)
    log.setLevel(level)
    log.propagate = propagate


def disable_logging() -> None:
    """Restore the default silent state.

    Sets the toolkit logger level back to ``NOTSET`` and re-enables
    the ``propagate = False`` guard so no records leak to the
    consumer's root logger.
    """
    log = _logging.getLogger(_TOOLKIT_LOGGER_NAME)
    log.setLevel(_logging.NOTSET)
    log.propagate = False

