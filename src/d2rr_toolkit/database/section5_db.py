"""Section 5 <-> D2RR Toolkit Database integration.

Template-based storage for D2R Reimagined Shared Stash Section 5
(Gems/Materials/Runes sub-tabs) items, plus a shared Gem Pool for
aggregate gem tracking.

## Storage model

- **section5_stacks** - one row per non-gem item_code (runes, worldstone
  shards, keys, relics, pliers, tools, organs, potions). Each row holds
  an unbounded `total_count` plus a single template blob that the writer
  uses with `clone_with_quantity()` to re-materialise any quantity.
- **gem_pool** - singleton row with the shared `total_count` across all
  gem types (Chipped -> Perfect * Ruby/Sapphire/Topaz/Emerald/Diamond/
  Amethyst/Skull). Rationale: the in-game Gem Bag converts between types
  freely, so the aggregate count is the meaningful number.
- **gem_templates** - one row per gem type ever seen, so the user can
  still pull a specific gem type out of the pool when they need it
  (for socketing, trade, etc.) without going through the Gem Bag in-game.

## Public API

    db = Section5Database("d2rr_archive.db")

    # Stack operations
    db.push_stack(item, count)          # item is a ParsedItem from a .d2i or .d2s
    parsed_item = db.pull_stack(code, count)   # returns a new ParsedItem
    db.get_stack_count(code)
    db.list_stacks()                    # list of StackRow

    # Gem pool operations
    db.push_gem(gem_item, count)
    parsed_item = db.pull_gem(gem_code, count)
    db.push_gem_cluster(cluster_item)   # rolls random[20,30], consumes the cluster
    db.get_gem_pool_count()
    db.list_gem_templates()             # list of gem_code strings

    # Rune conversion (pure arithmetic on section5_stacks)
    db.convert_runes_upgrade(rune_code)    # 2x rn -> 1x r(n+1)
    db.convert_runes_downgrade(rune_code)  # 1x rn -> 1x r(n-1)

Writer integration is done by the caller. All methods that return a
ParsedItem produce a blob with the requested quantity baked in - the
caller can then append it to a stash tab and pass the modified tab list
to `D2IWriter`.

[BV]
"""

from __future__ import annotations

import logging
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from d2rr_toolkit.database.modes import (
    GameMode,
    META_SCHEMA_SQL,
    SOFTCORE,
    bind_database_mode,
    default_archive_db_path,
)
from d2rr_toolkit.models.character import ParsedItem
from d2rr_toolkit.writers.item_utils import (
    SECTION5_MAX_QUANTITY,
    SECTION5_MIN_QUANTITY,
    clone_with_quantity,
)

logger = logging.getLogger(__name__)


# Gem item_code prefixes. Reimagined uses:
#   gc? = Chipped, gf? = Flawed, gs? = Standard, gl?/gz? = Flawless, gp? = Perfect
#   gm? = Reimagined "modern" standard gems (gmr, gme, gms, gmk, gmm, gmt)
#   gmd = Diamond (classic), gmo = Chaos Onyx
#   sku/skc/skf/skl/skz = Skull tiers
# [BV]
_GEM_PREFIXES: tuple[str, ...] = ("gc", "gf", "gs", "gl", "gz", "gp", "gm", "sk")
_GEM_CLUSTER_CODE = "1gc"
_GEM_CLUSTER_ROLL_MIN = 20
_GEM_CLUSTER_ROLL_MAX = 30

# Rune codes: r01 .. r33 in Reimagined (El through Zod). Range used by the
# conversion API; actual availability still requires a pre-seeded template.
_RUNE_MIN_INDEX = 1
_RUNE_MAX_INDEX = 33


def is_gem_code(item_code: str) -> bool:
    """Return True if `item_code` refers to a gem (any quality tier, any colour).

    Includes Skulls (sk*) which the game treats as gems. Excludes Gem Cluster
    (1gc) and Orbs (ooa/ooc/...) which are not actually gems despite living in
    the same sub-tab.
    """
    if not item_code:
        return False
    if item_code == _GEM_CLUSTER_CODE:
        return False
    # Skull variants: sku, skc, skf, skl, skz - 3 chars starting with 'sk'
    if len(item_code) == 3 and item_code.startswith("sk"):
        return True
    # Standard 3-char gem codes: first char 'g', second char in quality tier set
    if len(item_code) == 3 and item_code[0] == "g" and item_code[1] in "cfslzpm":
        return True
    return False


def is_gem_cluster(item_code: str) -> bool:
    """True if the code is the Gem Cluster (special random-roll item)."""
    return item_code == _GEM_CLUSTER_CODE


def rune_index(item_code: str) -> int | None:
    """Return the numeric index of a rune (1..33), or None if not a rune code."""
    if len(item_code) != 3 or item_code[0] != "r":
        return None
    try:
        n = int(item_code[1:])
    except ValueError:
        return None
    if _RUNE_MIN_INDEX <= n <= _RUNE_MAX_INDEX:
        return n
    return None


def rune_code(index: int) -> str:
    """Construct the rune item_code for a given 1..33 index."""
    if not _RUNE_MIN_INDEX <= index <= _RUNE_MAX_INDEX:
        raise ValueError(f"Rune index {index} out of range ({_RUNE_MIN_INDEX}..{_RUNE_MAX_INDEX})")
    return f"r{index:02d}"


# ─────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS section5_stacks (
    item_code            TEXT PRIMARY KEY,
    total_count          INTEGER NOT NULL DEFAULT 0,
    template_blob        BLOB NOT NULL,
    quantity_bit_offset  INTEGER NOT NULL,
    quantity_bit_width   INTEGER NOT NULL,
    flags_simple         INTEGER NOT NULL,
    first_seen_at        TEXT NOT NULL,
    last_modified_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gem_pool (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    total_count          INTEGER NOT NULL DEFAULT 0,
    last_modified_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gem_templates (
    gem_code             TEXT PRIMARY KEY,
    template_blob        BLOB NOT NULL,
    quantity_bit_offset  INTEGER NOT NULL,
    quantity_bit_width   INTEGER NOT NULL,
    flags_simple         INTEGER NOT NULL,
    first_seen_at        TEXT NOT NULL
);

-- Seed the singleton gem_pool row if missing.
INSERT OR IGNORE INTO gem_pool (id, total_count, last_modified_at)
VALUES (1, 0, datetime('now'));
"""


# ─────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class StackRow:
    """A stored non-gem stack entry."""

    item_code: str
    total_count: int
    first_seen_at: str
    last_modified_at: str
    # Template fields are exposed for write operations; callers normally
    # shouldn't need them.
    template_blob: bytes
    quantity_bit_offset: int
    quantity_bit_width: int
    flags_simple: bool


@dataclass
class GemTemplate:
    """A stored gem template (no per-type counter - the pool is shared)."""

    gem_code: str
    first_seen_at: str
    template_blob: bytes
    quantity_bit_offset: int
    quantity_bit_width: int
    flags_simple: bool


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class Section5DBError(Exception):
    """Base exception for Section 5 DB operations."""


class InsufficientCountError(Section5DBError):
    """Raised when a pull/convert would drop a count below zero."""


class TemplateMissingError(Section5DBError):
    """Raised when a pull targets a type we have never seen (no template)."""


class RuneBoundaryError(Section5DBError):
    """Raised for upgrades from r33 or downgrades from r01."""


# ─────────────────────────────────────────────────────────────────────────
# Helpers for ParsedItem template construction
# ─────────────────────────────────────────────────────────────────────────


def _extract_template_fields(item: ParsedItem) -> tuple[bytes, int, int, int]:
    """Extract (blob, bit_offset, bit_width, flags_simple) from a ParsedItem,
    validating that the item carries the quantity metadata the writer needs.

    Raises:
        ValueError: if the item has no source_data or no quantity metadata.
    """
    if item.source_data is None:
        raise ValueError(f"Item '{item.item_code}' has no source_data - cannot template.")
    if item.quantity_bit_offset is None:
        raise ValueError(
            f"Item '{item.item_code}' has no quantity_bit_offset - not stackable "
            f"or parser did not instrument its path."
        )
    return (
        bytes(item.source_data),
        int(item.quantity_bit_offset),
        int(item.quantity_bit_width),
        int(bool(item.flags.simple)),
    )


def _rehydrate_template(
    item_code: str,
    blob: bytes,
    bit_offset: int,
    bit_width: int,
    flags_simple: bool,
) -> ParsedItem:
    """Build a minimal ParsedItem from a stored template + the fields the
    writer needs. The returned item has enough metadata for
    `clone_with_quantity` to produce a new blob with any quantity in 1..99.

    We only need `flags.simple` for the writer's LSB-preservation logic;
    every other flag bit is already encoded inside `blob` and won't be
    re-read. We use `model_construct` to bypass Pydantic validation for
    the cosmetic fields we don't care about here.
    """
    from d2rr_toolkit.models.character import ItemFlags

    flags = ItemFlags.model_construct(
        identified=True,
        socketed=False,
        starter_item=False,
        simple=flags_simple,
        ethereal=False,
        personalized=False,
        runeword=False,
        location_id=0,
        equipped_slot=0,
        position_x=0,
        position_y=0,
        panel_id=5,
    )
    return ParsedItem.model_construct(
        item_code=item_code,
        flags=flags,
        source_data=blob,
        quantity_bit_offset=bit_offset,
        quantity_bit_width=bit_width,
        quantity=0,  # placeholder; clone_with_quantity computes the new raw value
        magical_properties=[],
        set_bonus_properties=[],
        set_bonus_mask=0,
        total_nr_of_sockets=0,
    )


# ─────────────────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────────────────


class Section5Database:
    """Persistent storage for Section 5 stacks + Gem Pool.

    Coexists with the existing ``items`` table in the same .db file,
    and shares its :mod:`~d2rr_toolkit.database.modes` game mode tag so
    SoftCore and HardCore inventories cannot be mixed.

    Args:
        db_path: Filesystem path to the SQLite file. In normal use the
            two game modes live in physically separate files; see
            :func:`open_section5_db` for the canonical factory.
        mode: Expected game mode. If omitted, the database is treated
            as softcore for backwards compatibility with pre-SC/HC code.
    """

    def __init__(
        self,
        db_path: str | Path,
        mode: GameMode | None = None,
    ) -> None:
        self._path = Path(db_path)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.executescript(META_SCHEMA_SQL)
        self._conn.commit()
        self._mode: GameMode = bind_database_mode(
            self._conn,
            mode if mode is not None else SOFTCORE,
            db_path=self._path,
        )
        logger.info(
            "Section5Database opened: %s [mode=%s]",
            self._path,
            self._mode,
        )

    @property
    def mode(self) -> GameMode:
        """Return the game mode this database is bound to."""
        return self._mode

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "Section5Database":
        """Support ``with Section5Database(...) as db:`` usage."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close the connection on context-manager exit, even on error."""
        self.close()

    # ── Stack operations ──────────────────────────────────────────────

    def push_stack(self, item: ParsedItem, count: int) -> None:
        """Add `count` units of a non-gem stack to the DB.

        If the item_code has never been seen, its template is persisted
        on this first push. Subsequent pushes of the same code only
        increment `total_count`.

        Raises:
            ValueError: if count < 1, or if item is a gem (use push_gem),
                        or if item is a Gem Cluster (use push_gem_cluster),
                        or if item is missing quantity metadata.
        """
        if count < 1:
            raise ValueError(f"push_stack count must be >= 1 (got {count})")
        if is_gem_code(item.item_code):
            raise ValueError(f"Item '{item.item_code}' is a gem - use push_gem() instead.")
        if is_gem_cluster(item.item_code):
            raise ValueError(f"Item '{item.item_code}' is a Gem Cluster - use push_gem_cluster().")
        blob, bit_off, bit_w, simple = _extract_template_fields(item)
        now = datetime.now().isoformat()
        row = self._conn.execute(
            "SELECT total_count FROM section5_stacks WHERE item_code = ?",
            (item.item_code,),
        ).fetchone()
        if row is None:
            self._conn.execute(
                """INSERT INTO section5_stacks
                   (item_code, total_count, template_blob, quantity_bit_offset,
                    quantity_bit_width, flags_simple, first_seen_at, last_modified_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (item.item_code, count, blob, bit_off, bit_w, simple, now, now),
            )
            logger.info("section5_stacks: seeded '%s' with count=%d", item.item_code, count)
        else:
            self._conn.execute(
                """UPDATE section5_stacks
                   SET total_count = total_count + ?, last_modified_at = ?
                   WHERE item_code = ?""",
                (count, now, item.item_code),
            )
            logger.info(
                "section5_stacks: incremented '%s' by %d (was %d)",
                item.item_code,
                count,
                row["total_count"],
            )
        self._conn.commit()

    def pull_stack(self, item_code: str, count: int) -> ParsedItem:
        """Remove `count` units of a stack and return a ParsedItem carrying
        a blob with `count` baked into its quantity field.

        The returned ParsedItem can be appended directly to a D2I tab list
        (or used with `patch_item_quantity` on an existing tab entry for
        in-place merging).

        Raises:
            TemplateMissingError: if no row exists for item_code.
            InsufficientCountError: if the DB holds fewer than `count` units.
            ValueError: if count is outside 1..SECTION5_MAX_QUANTITY.
        """
        if not SECTION5_MIN_QUANTITY <= count <= SECTION5_MAX_QUANTITY:
            raise ValueError(
                f"pull_stack count must be in {SECTION5_MIN_QUANTITY}..{SECTION5_MAX_QUANTITY} "
                f"(got {count}). To pull more, call multiple times and merge in the tab."
            )
        row = self._conn.execute(
            "SELECT * FROM section5_stacks WHERE item_code = ?", (item_code,)
        ).fetchone()
        if row is None:
            raise TemplateMissingError(
                f"No template for '{item_code}' - push at least 1 unit of it first."
            )
        if row["total_count"] < count:
            raise InsufficientCountError(
                f"DB has only {row['total_count']} of '{item_code}', requested {count}."
            )
        now = datetime.now().isoformat()
        self._conn.execute(
            """UPDATE section5_stacks
               SET total_count = total_count - ?, last_modified_at = ?
               WHERE item_code = ?""",
            (count, now, item_code),
        )
        self._conn.commit()
        template = _rehydrate_template(
            item_code=item_code,
            blob=row["template_blob"],
            bit_offset=row["quantity_bit_offset"],
            bit_width=row["quantity_bit_width"],
            flags_simple=bool(row["flags_simple"]),
        )
        return clone_with_quantity(template, count)

    def get_stack_count(self, item_code: str) -> int:
        """Return the stored count for `item_code`, or 0 if unknown."""
        row = self._conn.execute(
            "SELECT total_count FROM section5_stacks WHERE item_code = ?",
            (item_code,),
        ).fetchone()
        return row["total_count"] if row else 0

    def list_stacks(self) -> list[StackRow]:
        """Return all non-gem stacks currently stored (including count=0 entries
        kept for their template)."""
        rows = self._conn.execute("SELECT * FROM section5_stacks ORDER BY item_code").fetchall()
        return [
            StackRow(
                item_code=r["item_code"],
                total_count=r["total_count"],
                first_seen_at=r["first_seen_at"],
                last_modified_at=r["last_modified_at"],
                template_blob=r["template_blob"],
                quantity_bit_offset=r["quantity_bit_offset"],
                quantity_bit_width=r["quantity_bit_width"],
                flags_simple=bool(r["flags_simple"]),
            )
            for r in rows
        ]

    # ── Gem pool operations ───────────────────────────────────────────

    def push_gem(self, item: ParsedItem, count: int) -> None:
        """Add `count` gems of a specific type to the shared pool.

        The gem's template is persisted in `gem_templates` on first sight,
        but the counter lives in `gem_pool` and is shared with every other
        gem type.

        Raises:
            ValueError: if count < 1, or if item is not a gem, or if the
                        item is missing quantity metadata.
        """
        if count < 1:
            raise ValueError(f"push_gem count must be >= 1 (got {count})")
        if not is_gem_code(item.item_code):
            raise ValueError(
                f"Item '{item.item_code}' is not a gem. Use push_stack() or "
                f"push_gem_cluster() instead."
            )
        blob, bit_off, bit_w, simple = _extract_template_fields(item)
        now = datetime.now().isoformat()
        # Insert template if missing
        existing = self._conn.execute(
            "SELECT 1 FROM gem_templates WHERE gem_code = ?", (item.item_code,)
        ).fetchone()
        if existing is None:
            self._conn.execute(
                """INSERT INTO gem_templates
                   (gem_code, template_blob, quantity_bit_offset,
                    quantity_bit_width, flags_simple, first_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item.item_code, blob, bit_off, bit_w, simple, now),
            )
            logger.info("gem_templates: seeded '%s'", item.item_code)
        # Increment the shared pool
        self._conn.execute(
            """UPDATE gem_pool SET total_count = total_count + ?,
               last_modified_at = ? WHERE id = 1""",
            (count, now),
        )
        self._conn.commit()

    def pull_gem(self, gem_code: str, count: int) -> ParsedItem:
        """Pull `count` gems of a specific type out of the shared pool.

        The pool total must be at least `count`, AND the requested gem_code
        must already have a template in `gem_templates` (i.e. the user has
        pushed at least one gem of that type at some point).

        Raises:
            TemplateMissingError: if no template exists for `gem_code`.
            InsufficientCountError: if the pool has fewer than `count` gems.
            ValueError: for invalid inputs.
        """
        if not is_gem_code(gem_code):
            raise ValueError(f"'{gem_code}' is not a gem code.")
        if not SECTION5_MIN_QUANTITY <= count <= SECTION5_MAX_QUANTITY:
            raise ValueError(
                f"pull_gem count must be in {SECTION5_MIN_QUANTITY}..{SECTION5_MAX_QUANTITY}"
            )
        tpl_row = self._conn.execute(
            "SELECT * FROM gem_templates WHERE gem_code = ?", (gem_code,)
        ).fetchone()
        if tpl_row is None:
            raise TemplateMissingError(
                f"No template for gem '{gem_code}' - push at least 1 of it into the "
                f"DB first so we can remember how to serialise it."
            )
        pool_row = self._conn.execute("SELECT total_count FROM gem_pool WHERE id = 1").fetchone()
        if pool_row["total_count"] < count:
            raise InsufficientCountError(
                f"Gem pool has only {pool_row['total_count']} gems, requested {count}."
            )
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE gem_pool SET total_count = total_count - ?, last_modified_at = ? WHERE id = 1",
            (count, now),
        )
        self._conn.commit()
        template = _rehydrate_template(
            item_code=gem_code,
            blob=tpl_row["template_blob"],
            bit_offset=tpl_row["quantity_bit_offset"],
            bit_width=tpl_row["quantity_bit_width"],
            flags_simple=bool(tpl_row["flags_simple"]),
        )
        return clone_with_quantity(template, count)

    def push_gem_cluster(self, cluster_item: ParsedItem, rng: random.Random | None = None) -> int:
        """Consume a Gem Cluster (1gc) and roll random[20..30] gems into the pool.

        The Cluster item itself is NOT persisted - we treat the cube-with-Gem-Bag
        outcome as the canonical "what this item is worth" and short-circuit it.

        Args:
            cluster_item: ParsedItem with item_code='1gc'. Only the code is
                          checked; source_data/quantity are ignored.
            rng:          Optional seeded RNG for deterministic tests.

        Returns:
            The rolled gem count (20..30 inclusive) that was added to the pool.

        Raises:
            ValueError: if cluster_item is not a Gem Cluster.
        """
        if not is_gem_cluster(cluster_item.item_code):
            raise ValueError(
                f"Item '{cluster_item.item_code}' is not a Gem Cluster (expected '1gc')."
            )
        rng = rng or random.Random()
        rolled = rng.randint(_GEM_CLUSTER_ROLL_MIN, _GEM_CLUSTER_ROLL_MAX)
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE gem_pool SET total_count = total_count + ?, last_modified_at = ? WHERE id = 1",
            (rolled, now),
        )
        self._conn.commit()
        logger.info("gem_pool: Gem Cluster rolled %d gems", rolled)
        return rolled

    def get_gem_pool_count(self) -> int:
        """Return the pooled gem count (singleton row)."""

        row = self._conn.execute("SELECT total_count FROM gem_pool WHERE id = 1").fetchone()
        return row["total_count"] if row else 0

    def list_gem_templates(self) -> list[GemTemplate]:
        """Return all cached gem template records as a list."""

        rows = self._conn.execute("SELECT * FROM gem_templates ORDER BY gem_code").fetchall()
        return [
            GemTemplate(
                gem_code=r["gem_code"],
                first_seen_at=r["first_seen_at"],
                template_blob=r["template_blob"],
                quantity_bit_offset=r["quantity_bit_offset"],
                quantity_bit_width=r["quantity_bit_width"],
                flags_simple=bool(r["flags_simple"]),
            )
            for r in rows
        ]

    # ── Rune conversion ──────────────────────────────────────────────

    def convert_runes_upgrade(self, source_code: str) -> str:
        """Convert 2* `source_code` into 1* next-higher rune.

        Returns the produced rune code. Both rune types must already be known
        to the DB (i.e. their templates must exist) - seed the target type
        once before calling this if it's the user's first time owning it.

        Raises:
            ValueError: if source is not a rune.
            RuneBoundaryError: if source is r33 (Zod, cannot upgrade).
            InsufficientCountError: if DB has fewer than 2 of source.
            TemplateMissingError: if the target rune has no stored template.
        """
        idx = rune_index(source_code)
        if idx is None:
            raise ValueError(f"'{source_code}' is not a rune code (r01..r33).")
        if idx == _RUNE_MAX_INDEX:
            raise RuneBoundaryError(f"Cannot upgrade '{source_code}' - already at maximum tier.")
        target_code = rune_code(idx + 1)
        self._validate_conversion(source_code, target_code, source_needed=2)

        now = datetime.now().isoformat()
        self._conn.execute(
            """UPDATE section5_stacks SET total_count = total_count - 2,
               last_modified_at = ? WHERE item_code = ?""",
            (now, source_code),
        )
        self._conn.execute(
            """UPDATE section5_stacks SET total_count = total_count + 1,
               last_modified_at = ? WHERE item_code = ?""",
            (now, target_code),
        )
        self._conn.commit()
        logger.info("convert_runes_upgrade: 2x %s -> 1x %s", source_code, target_code)
        return target_code

    def convert_runes_downgrade(self, source_code: str) -> str:
        """Convert 1* `source_code` into 1* next-lower rune.

        Returns the produced rune code.

        Raises:
            ValueError: if source is not a rune.
            RuneBoundaryError: if source is r01 (El, cannot downgrade).
            InsufficientCountError: if DB has fewer than 1 of source.
            TemplateMissingError: if the target rune has no stored template.
        """
        idx = rune_index(source_code)
        if idx is None:
            raise ValueError(f"'{source_code}' is not a rune code (r01..r33).")
        if idx == _RUNE_MIN_INDEX:
            raise RuneBoundaryError(f"Cannot downgrade '{source_code}' - already at minimum tier.")
        target_code = rune_code(idx - 1)
        self._validate_conversion(source_code, target_code, source_needed=1)

        now = datetime.now().isoformat()
        self._conn.execute(
            """UPDATE section5_stacks SET total_count = total_count - 1,
               last_modified_at = ? WHERE item_code = ?""",
            (now, source_code),
        )
        self._conn.execute(
            """UPDATE section5_stacks SET total_count = total_count + 1,
               last_modified_at = ? WHERE item_code = ?""",
            (now, target_code),
        )
        self._conn.commit()
        logger.info("convert_runes_downgrade: 1x %s -> 1x %s", source_code, target_code)
        return target_code

    def _validate_conversion(self, source_code: str, target_code: str, source_needed: int) -> None:
        """Shared validation for upgrade/downgrade: both templates exist and
        source has enough count."""
        src_row = self._conn.execute(
            "SELECT total_count FROM section5_stacks WHERE item_code = ?",
            (source_code,),
        ).fetchone()
        if src_row is None:
            raise TemplateMissingError(
                f"No template for source rune '{source_code}' - push at least 1 first."
            )
        if src_row["total_count"] < source_needed:
            raise InsufficientCountError(
                f"Need {source_needed}x '{source_code}' for conversion, "
                f"DB has {src_row['total_count']}."
            )
        tgt_row = self._conn.execute(
            "SELECT 1 FROM section5_stacks WHERE item_code = ?", (target_code,)
        ).fetchone()
        if tgt_row is None:
            raise TemplateMissingError(
                f"No template for target rune '{target_code}' - push at least 1 of it "
                f"first so we can serialise the conversion result."
            )


def open_section5_db(
    mode: GameMode,
    *,
    base_dir: Path | None = None,
    db_path: Path | None = None,
) -> Section5Database:
    """Open (or create) the mode-specific Section 5 database.

    A thin convenience over :class:`Section5Database` that builds the
    canonical mode-specific filename via
    :func:`d2rr_toolkit.database.modes.default_archive_db_path` - the
    Section 5 tables share the archive DB's SQLite file, so the path
    is identical to the one used by :func:`open_item_db`.

    Args:
        mode: ``"softcore"`` or ``"hardcore"``.
        base_dir: Directory in which to place the DB file. Defaults to
            the current working directory. Ignored when ``db_path`` is
            supplied.
        db_path: Explicit path override. The mode tag is still
            validated against the DB's meta table.

    Returns:
        An opened :class:`Section5Database` bound to *mode*.

    Raises:
        DatabaseModeMismatchError: If the target file already exists
            and carries a different mode tag.
    """
    if db_path is None:
        db_path = default_archive_db_path(mode, base_dir=base_dir)
    return Section5Database(db_path, mode=mode)
