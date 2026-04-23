# Library Logging Convention

`d2rr_toolkit` follows Python's standard "library logging" convention:
**silent by default**, with consumers opting in explicitly when they
want to see records.  This document is the reference for how the
toolkit's logging is wired and how to turn it up or down from a
consuming application.

## The contract

1. Importing `d2rr_toolkit` (or any submodule) produces **zero** log
   output.  No handler attaches to the root logger, no
   `basicConfig` call is made, no records leak to a consumer's
   handlers through the propagation chain.
2. The top-level `d2rr_toolkit` logger has a `NullHandler` attached
   and `propagate = False`.  Records emitted anywhere in the package
   stop at that null handler unless the consumer has explicitly
   asked to see them.
3. Hot-path `logger.debug(...)` calls are guarded with
   `logger.isEnabledFor(logging.DEBUG)` so that argument evaluation
   + `LogRecord` construction cost is paid only when DEBUG is
   actually enabled.
4. No submodule calls `logging.basicConfig` or attaches handlers to
   the **root** logger - those APIs are the consumer's prerogative.

The rationale is the Python Logging HOWTO's "Configuring Logging
for a Library" chapter, and the reference implementation is the
`requests` library's `__init__.py`.

## Silent by default - what this means for consumers

A consumer that imports the toolkit and does nothing else gets no
log output at all:

```python
import d2rr_toolkit                         # zero stderr bytes
from d2rr_toolkit.parsers.d2s_parser import D2SParser
char = D2SParser(path).parse()              # zero log records emitted
```

A consumer that *has* configured logging (root handlers, Qt log
sink, file rotator, pytest `caplog`, ...) still sees nothing from the
toolkit, because propagation is off.  This is the main performance
win: consumers no longer get ~12 000 DEBUG records per parse routed
through their (potentially slow) handler.

## Opting in

Two equivalent paths; pick whichever matches the consumer's style.

### The convenience helper

```python
from d2rr_toolkit.logging import enable_logging

enable_logging()                      # INFO and above
enable_logging(level=logging.DEBUG)   # everything (~7500 records/parse)
enable_logging(propagate=False)       # don't feed toolkit records to
                                      # the consumer's root handlers
```

The module name deliberately shadows the stdlib `logging` **only**
inside the `d2rr_toolkit` namespace - Python's absolute imports mean
every other `import logging` still resolves to the stdlib.  The
module docstring repeats this warning for the next reader.

### The stdlib form

```python
import logging
logging.getLogger("d2rr_toolkit").setLevel(logging.INFO)
logging.getLogger("d2rr_toolkit").propagate = True
```

Identical effect.  Use it when the consumer already threads
loggers through a config file or a dictConfig / fileConfig
invocation.

### Turning it back off

```python
from d2rr_toolkit.logging import disable_logging
disable_logging()    # level NOTSET + propagate False (the default state)
```

## API

### `d2rr_toolkit.logging.enable_logging(level=logging.INFO, *, propagate=True) -> None`

Set the `d2rr_toolkit` logger's level and propagation flag.  Calling
with no arguments is the INFO-and-above opt-in.  Passing
`propagate=False` keeps the toolkit's records contained to
handlers directly attached to the `d2rr_toolkit` logger (useful
when the consumer routes every logger through a dedicated sink).

### `d2rr_toolkit.logging.disable_logging() -> None`

Restore the silent default state: level `NOTSET`, `propagate=False`.
Idempotent - safe to call at any time, including from shutdown
handlers that reset global state.

## Hot-path guard pattern

Every DEBUG-level call inside a tight loop follows this pattern:

```python
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Stat %d (%s) = %s (raw=%d)",
                 stat_id, field_name, value, raw)
```

The level check is ~1 microsecond.  The original unguarded call's
argument evaluation + `LogRecord` construction is ~5-10 µs even in
the no-output case - for 12 000 calls per parse, that's ~100 ms of
main-thread time saved when DEBUG is off (the normal state).

`D2SParser.parse()` applies this pattern to every one of its 56
hot-path `logger.debug(...)` calls.  Other modules
(`d2i_parser`, `bit_reader`, `bulk_loader`, `sprites/resolver`,
`display/palette`, `display/tinted_sprite`, `game_data/*`) either
have no DEBUG calls in tight loops or are already guarded - an AST
scan in the regression test confirms this each time it runs.

## Performance expectations

Measured on a typical consumer-grade NVMe SSD with the Qt log
handler the GUI ships:

| Scenario | Records emitted | `parse()` median |
|---|---:|---:|
| Default (silent), consumer has no root handler | 0 | ~12 ms |
| Default (silent), consumer has a slow root DEBUG handler | 0 | ~90 ms |
| `enable_logging(INFO)` | ~24 | ~15 ms |
| `enable_logging(DEBUG)` | ~7 500 | ~5 000 ms |

The "slow root DEBUG handler" row is the important one - it's the
scenario every GUI used to hit whenever its own log level was
DEBUG.  Since nothing from the toolkit reaches the consumer's
handlers without an explicit opt-in, the 90 ms figure holds
regardless of how slow the consumer's handlers are.

## Regression guard

`tests/test_toolkit_logging_hygiene.py` - 26 checks covering:

| # | What is verified |
|---|---|
| AC1 | Silent-by-default: zero stderr bytes on a bare `import`. |
| AC2 | A slow root DEBUG handler does not slow `parse()` down (< 200 ms). |
| AC3 | Opt-in tiers emit the expected record counts (0 / 24+ / 7000+). |
| AC4 | AST scan: zero `print()` calls in library code. |
| AC5 | AST scan: zero `basicConfig` / root-level `addHandler` calls. |
| AC6 | `parse()` median stays under 100 ms in the default state. |
| AC7 | `d2rr_toolkit` logger starts with `NullHandler` + `propagate=False` + `level=NOTSET`. |
| AC8 | `disable_logging()` returns the logger to exactly the default state. |
| AC9 | Namespace safety: after importing `d2rr_toolkit.logging`, the stdlib `logging.INFO` constant is still `20`. |

The same suite also asserts that no DEBUG record emitted from a
tight loop is missing its `isEnabledFor` guard - an AST walker
fails the run if any future change regresses the pattern.

## References

* Python Logging HOWTO - "Configuring Logging for a Library":
  <https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library>
* `logging.NullHandler` reference:
  <https://docs.python.org/3/library/logging.handlers.html#logging.NullHandler>
* `requests` library `__init__.py` - canonical NullHandler
  reference implementation.


