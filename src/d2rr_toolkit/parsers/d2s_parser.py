"""D2S character file and D2I shared stash binary item parser.

Parses Diablo II: Resurrected (v105) save files with Reimagined mod support.
Handles Huffman-encoded item codes, ISC property lists, Set/Unique bonus
lists, runeword display properties, socket children, and mercenary items.

Public API:
    D2SParser(path).parse() -> ParsedCharacter
    parse_d2i_tab_from_bytes(data, start, end) -> (items, offset, end, count)
    parse_item_from_bytes(source_data) -> ParsedItem
    parse_character_header(path) -> CharacterHeader

Binary format details: see docs/spec/d2s_format_spec.md
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from d2rr_toolkit.constants import (
    # Signature / version
    D2S_SIGNATURE,
    SUPPORTED_VERSIONS,
    # Header offsets [BV]
    OFFSET_CHECKSUM,
    OFFSET_CLASS,
    OFFSET_FILE_SIZE,
    OFFSET_LEVEL,
    OFFSET_NAME,
    OFFSET_PROGRESSION,
    OFFSET_SIGNATURE,
    OFFSET_STATUS,
    OFFSET_STATS_SECTION,
    OFFSET_VERSION,
    HEADER_SIZE_V105,
    # Section markers [BV]
    SECTION_MARKER_STATS,
)
from d2rr_toolkit.exceptions import (
    InvalidSignatureError,
    SpecVerificationError,
    UnsupportedVersionError,
)
from d2rr_toolkit.game_data.charstats import get_charstats_db
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db, load_item_stat_cost
from d2rr_toolkit.game_data.item_types import get_item_type_db
from d2rr_toolkit.game_data.skills import get_skill_db
from d2rr_toolkit.models.character import (
    CharacterHeader,
    ParsedCharacter,
    ParsedItem,
)
from d2rr_toolkit.parsers.bit_reader import BitReader
from d2rr_toolkit.parsers.exceptions import GameDataNotLoadedError

logger = logging.getLogger(__name__)


# _QUALITY_READERS moved to d2s_parser_items.py alongside
# the _read_qsd_* methods it dispatches to.


# ``GameDataNotLoadedError`` is defined in ``d2rr_toolkit.parsers.exceptions``
# and re-exported here for backward compatibility - the canonical import is
# now ``from d2rr_toolkit.parsers.exceptions import GameDataNotLoadedError``.
# (Leaving ``__all__`` unset to preserve ``from d2s_parser import *`` semantics
# for the rest of the module's public names.)


def _ensure_game_data_loaded() -> None:
    """Assert the parser's hard prerequisites are populated.

    Checks the three singletons that :meth:`_parse_single_item` depends on.
    Raises :class:`GameDataNotLoadedError` with a precise, pointed message
    if any of them is empty.

    Kept private because callers should not need this guard - the parser
    entry points call it themselves. Exposed via fail-loud so that a
    misconfigured environment produces a stack trace at the entry point,
    not garbage 300 items later.
    """
    missing: list[str] = []
    if not get_item_type_db().is_loaded():
        missing.append("item_types (call load_item_types())")
    if not get_isc_db().is_loaded():
        missing.append("item_stat_cost (call load_item_stat_cost())")
    if not get_skill_db().is_loaded():
        missing.append("skills (call load_skills())")
    if missing:
        raise GameDataNotLoadedError(
            "Parser prerequisites not loaded: "
            + ", ".join(missing)
            + ". Without these, _parse_single_item silently degrades to "
            "'Unknown category -> speculative property read', which "
            "produces bit-misaligned garbage and loses 90%+ of items "
            "without surfacing an error. Fix: either call the loaders "
            "yourself, or rely on the parser's auto-load path "
            "(D2IParser.parse / D2SParser.parse). If you hit this from "
            "a test, add the loader calls to the test setup."
        )


def _auto_load_game_data() -> None:
    """Lazy-load the parser's hard prerequisites via the cached loaders.

    The Iron Rule loaders are cheap on a warm cache (pickle hit), so this
    is safe to call unconditionally at every parse entry. Any loader failure
    propagates so callers see the root cause.

    Kept separate from :func:`_ensure_game_data_loaded` so tests can
    exercise the fail-loud path without side-effects.

    Loads: item_types, item_stat_cost, skills, charstats (D2S character
    headers need class-name resolution).
    """
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.skills import load_skills

    if not get_item_type_db().is_loaded():
        load_item_types()
    if not get_isc_db().is_loaded():
        load_item_stat_cost()
    if not get_skill_db().is_loaded():
        load_skills()
    if not get_charstats_db().is_loaded():
        load_charstats()


# Character stats: field names (Python-side names, NOT from any excel file)
# [BV]  Stat IDs 0-15 are the character stat section IDs.
_STAT_ID_TO_FIELD: dict[int, str] = {
    0: "strength",
    1: "energy",
    2: "dexterity",
    3: "vitality",
    4: "stat_points_remaining",
    5: "skill_points_remaining",
    6: "current_hp",
    7: "max_hp",
    8: "current_mana",
    9: "max_mana",
    10: "current_stamina",
    11: "max_stamina",
    12: "level",
    13: "experience",
    14: "gold_inventory",
    15: "gold_stash",
}

# Stats 6-11 are HP/Mana/Stamina stored as 1/256-unit fixed-point values.
# This is game-engine binary format knowledge NOT present in any excel file.
# [BV]
_CHAR_STAT_FIXED_POINT: frozenset[int] = frozenset({6, 7, 8, 9, 10, 11})

# NOTE: Character stat bit-widths are read from ItemStatCost.txt at runtime
# (CSvBits column). The ISC MUST be loaded before parsing character stats.
# There are NO hardcoded fallback values - if ISC is not loaded, parsing
# will raise an error. This keeps us tied to the real game data.


from d2rr_toolkit.parsers.d2s_parser_header import HeaderParserMixin  # noqa: E402
from d2rr_toolkit.parsers.d2s_parser_items import ItemsParserMixin  # noqa: E402
from d2rr_toolkit.parsers.d2s_parser_merc import MercenaryParserMixin  # noqa: E402
from d2rr_toolkit.parsers.d2s_parser_stats import StatsSkillsParserMixin  # noqa: E402


class D2SParser(
    HeaderParserMixin,
    StatsSkillsParserMixin,
    ItemsParserMixin,
    MercenaryParserMixin,
):
    """Parser for D2S character save files (v105, D2R Reimagined).

    Usage:
        parser = D2SParser(Path("character.d2s"))
        character = parser.parse()
        print(character.header.character_name)
        print(f"{len(character.items)} items found")

    All field positions in this parser are [BV]
    Fields marked [SPEC_ONLY] are validated at parse time and will raise
    SpecVerificationError if the binary contradicts the assumption.

    Structure (post parser-split refactor):
      * ``HeaderParserMixin`` (d2s_parser_header.py) - ``_parse_header``
      * ``StatsSkillsParserMixin`` (d2s_parser_stats.py)
      * ``ItemsParserMixin`` (d2s_parser_items.py)
      * ``MercenaryParserMixin`` (d2s_parser_merc.py)
    """

    def __init__(self, path: Path) -> None:
        """Initialize the parser with a path to the .d2s file.

        Args:
            path: Path to the .d2s character save file.
        """
        self._path = path
        self._data: bytes = b""
        self._reader: BitReader | None = None
        self._trailing_item_bytes: bytes | None = None
        # D2I section boundary: set by parse_d2i_tab_from_bytes() to prevent
        # _skip_inter_item_padding from probing past the section end into the
        # next section's header. None = unlimited (D2S files have no sections).
        #
        self._section_end_byte: int | None = None

    def _require_reader(self) -> BitReader:
        """Return ``self._reader`` as a non-None ``BitReader`` or raise.

        Replaces the ``assert self._reader is not None`` type-narrowing
        pattern repeated throughout the parser mixins. The assert was
        stripped under ``python -O``, leaving a less-diagnosable
        ``AttributeError`` at the next ``self._reader.read(...)``.
        This helper survives ``-O`` and gives the operator a clear
        error message.

        Raises:
            RuntimeError: if ``parse()`` has not been called yet.

        Returns:
            The live :class:`BitReader` bound to the parser.
        """
        if self._reader is None:
            raise RuntimeError(
                f"{type(self).__name__}: reader not initialised. "
                "Parser must be primed via parse() before accessing items."
            )
        return self._reader

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def parse(self) -> ParsedCharacter:
        """Parse the entire .d2s file and return the character data.

        Returns:
            ParsedCharacter with header, stats, and item list populated.

        Raises:
            InvalidSignatureError:   Bad magic bytes.
            UnsupportedVersionError: Version not in SUPPORTED_VERSIONS.
            SpecVerificationError:   [SPEC_ONLY] assumption violated.
            FileNotFoundError:       File does not exist.
        """
        logger.info("Parsing D2S file: %s", self._path)
        # Auto-load parser prerequisites - cheap on warm cache, prevents
        # the silent 90%-item-loss bug when callers forget to initialise.
        _auto_load_game_data()
        _ensure_game_data_loaded()
        self._data = self._path.read_bytes()
        self._reader = BitReader(self._data)

        header = self._parse_header()
        logger.info(
            "Character: %s (%s) Level %d",
            header.character_name,
            header.character_class_name,
            header.level,
        )

        stats = self._parse_stats()
        logger.info("Stats parsed. Level=%d Gold=%d", stats.level, stats.gold_inventory)

        # Merc header lives in the D2S header area (14 bytes at 0xA1).
        # It is independent of the merc ITEM list which comes later.
        mercenary = self._parse_mercenary_header()
        if mercenary is not None:
            logger.info(
                "Merc header: type=%d (%s D%d), name_id=%d, exp=%d",
                mercenary.type_id,
                mercenary.hireling_class or "unknown",
                mercenary.hireling_difficulty,
                mercenary.name_id,
                mercenary.experience,
            )

        self._skip_skills()

        items = self._parse_item_list()
        logger.info("Parsed %d items", len(items))

        # Merc items live in the 'jf' section right after the corpse JM.
        # The parser progresses through it even if merc_count == 0.
        self._parse_merc_section()
        logger.info("Parsed %d merc items", len(self._merc_items))

        # jm_count_byte_offset points to the uint16 AFTER 'JM' - the marker itself is 2 bytes before.
        items_jm_byte_offset = (
            (self._jm_count_byte_offset - 2)
            if hasattr(self, "_jm_count_byte_offset") and self._jm_count_byte_offset is not None
            else None
        )
        corpse_jm_byte_offset = (
            self._corpse_jm_byte_offset if hasattr(self, "_corpse_jm_byte_offset") else None
        )
        merc_jm_byte_offset = (
            self._merc_jm_byte_offset if hasattr(self, "_merc_jm_byte_offset") else None
        )

        return ParsedCharacter(
            header=header,
            stats=stats,
            mercenary=mercenary,
            items=items,
            merc_items=list(self._merc_items),
            items_jm_byte_offset=items_jm_byte_offset,
            corpse_jm_byte_offset=corpse_jm_byte_offset,
            merc_jm_byte_offset=merc_jm_byte_offset,
            trailing_item_bytes=self._trailing_item_bytes,
        )

    @classmethod
    def _create_reader(cls, data: bytes, start_byte: int = 0) -> "D2SParser":
        """Create a D2SParser instance with a BitReader for in-memory data.

        Used by classmethods that parse item lists from raw byte buffers
        (shared between D2S and D2I parsers).
        """
        instance = cls.__new__(cls)
        instance._path = Path("<in-memory>")
        instance._data = data
        instance._reader = BitReader(data, start_byte=start_byte)
        instance._trailing_item_bytes = None
        instance._section_end_byte = None
        return instance

    @classmethod
    def parse_d2i_tab_from_bytes(
        cls,
        data: bytes,
        start_byte: int = 0,
        *,
        section_end_byte: int | None = None,
    ) -> tuple[list[ParsedItem], int, int, int]:
        """Parse one D2I stash tab: JM-counted items + extra items after JM.

        D2I JM count = root items only (excludes socket children).
        Socket children follow their parent in the byte stream but are
        NOT counted. Extra items (regular stash items past the JM
        boundary) are also uncounted. [BV TC67]

        Args:
            data:             Raw file bytes.
            start_byte:       Byte offset where the JM marker begins.
            section_end_byte: Byte offset where this D2I section ENDS
                              (exclusive). Limits padding probes + item
                              source_data extraction.

        Returns:
            (all_items, jm_count_byte_offset, end_byte, jm_item_count):
            - all_items: JM items followed by extra items (one flat list)
            - jm_count_byte_offset: byte offset of the uint16 JM count
            - end_byte: byte-aligned position after the last parsed item
            - jm_item_count: how many items came from the JM-counted region
        """
        # Auto-load + fail-loud: without these, classify() returns UNKNOWN
        # for every valid item code and the parser loses 90%+ of items.
        _auto_load_game_data()
        _ensure_game_data_loaded()
        instance = cls._create_reader(data, start_byte)
        instance._section_end_byte = section_end_byte
        jm_items, jm_count_byte_offset = instance._parse_jm_items()
        jm_item_count = len(jm_items)
        extra_items = instance._parse_socket_children(jm_items)
        all_items = jm_items + extra_items
        reader = instance._require_reader()
        end_byte = (reader.bit_pos + 7) // 8

        # ── Completeness health-check ────────────────────────────────────
        # Compare parsed-item byte coverage against the section payload. A
        # large gap means the parser surfaced fewer items than the section
        # actually contains - typically caused by a recovery skip (JM loop)
        # or an early-exit in _parse_socket_children (see P3 note below).
        # The writer's orphan-extras refusal (D2IOrphanExtrasError) will
        # catch any attempt to write such a section empty, but we also
        # warn here so the loss doesn't go unnoticed in callers that only
        # inspect items.
        #
        # [P3 - known limitation]  Tab 1 of the user's live SharedStash
        # ModernSharedStashSoftCoreV2.d2i leaks ~81 bytes (~3 items:
        # 1 lost to recovery at item 25, 2 small charms missed by the
        # socket-children loop after consecutive_failures>=2). Root cause
        # is deeper and tracked separately; this warning surfaces it so
        # GUI/CLI users see the incomplete parse instead of silently
        # working with partial data.
        if section_end_byte is not None and all_items:
            # Measure parsed coverage from the first item's start up to the
            # end of the last item's source_data.
            parsed_bytes = 0
            for it in all_items:
                if it.source_data:
                    parsed_bytes += len(it.source_data)
                for child in it.socket_children:
                    if child.source_data:
                        parsed_bytes += len(child.source_data)
            items_start = start_byte + 4  # JM(2) + count(2)
            section_payload = section_end_byte - items_start
            if section_payload > 0:
                gap = section_payload - parsed_bytes
                # Tolerate <= 2 bytes (normal inter-section padding).
                if gap > 2:
                    logger.warning(
                        "Parser completeness gap: %d/%d bytes of section "
                        "starting at 0x%X went unparsed (%.1f%% loss). "
                        "Tail may contain real items the parser missed. "
                        "Empty-out on this section will be refused by the "
                        "writer's orphan-extras guard.",
                        gap,
                        section_payload,
                        start_byte,
                        100.0 * gap / section_payload,
                    )
        return all_items, jm_count_byte_offset, end_byte, jm_item_count

    # ──────────────────────────────────────────────────────────
    # Header parsing [BV]
    # ──────────────────────────────────────────────────────────

    # _parse_header moved to d2s_parser_header.py.

    # _parse_mercenary_header moved to d2s_parser_merc.py.

    # _parse_stats + _skip_skills moved to d2s_parser_stats.py.

    # ──────────────────────────────────────────────────────────
    # Item list parsing [BV]
    # ──────────────────────────────────────────────────────────

    # All item-parsing methods moved to d2s_parser_items.py.


def parse_item_from_bytes(source_data: bytes) -> ParsedItem:
    """Reconstruct a fully parsed item from its serialised source_data bytes.

    This is the **public API** for re-parsing items that were previously
    extracted and stored (e.g. in the ItemDatabase / SQLite). The returned
    ``ParsedItem`` is identical to what ``D2SParser.parse()`` would produce
    for the same item bytes embedded in a character file.

    Typical use-case - the GUI's Ledger tab needs to render archived items
    that only exist as ``source_data`` blobs in the DB::

        from d2rr_toolkit.parsers.d2s_parser import parse_item_from_bytes

        parsed = parse_item_from_bytes(stored_item.source_data)
        pixmap = pixmap_factory.build(png, parsed, ...)
        tooltip = build_tooltip_document(parsed, ...)

    **Prerequisites:** The same game-data loaders that a full parse needs
    must be loaded before calling this function - at minimum
    ``load_item_types()``, ``load_item_stat_cost()``, ``load_skills()``.
    In the standard GUI boot sequence these are already loaded.

    **Thread safety:** The function is stateless between calls (creates a
    fresh parser instance each time). It is safe to call from any thread
    as long as the game-data singletons were loaded during startup.

    **Socket children:** Must be parsed individually - each child is stored
    as a separate DB entry with its own ``source_data``. Call this function
    once per child.

    Args:
        source_data: Raw item bytes exactly as stored in
            ``ParsedItem.source_data``.

    Returns:
        A fully populated ``ParsedItem`` with all fields set: ``flags``,
        ``extended``, ``magical_properties``, ``armor_data``, ``quantity``,
        ``display_quantity``, ``unique_type_id``, ``set_item_id``,
        ``prefix_id``, ``suffix_id``, ``rare_name_id1/2``,
        ``runeword_id``, ``total_nr_of_sockets``, ``set_bonus_properties``,
        ``runeword_properties``, etc.

    Raises:
        Exception: If the bytes cannot be parsed (corrupt data, unknown
            Huffman code, missing game-data tables, etc.).
    """
    # Pad the source_data with 0xFF bytes to provide a synthetic 0x1FF
    # terminator for the property reader. Some items' source_data blobs
    # end at the exact bit boundary of the last property - the real 0x1FF
    # terminator was captured in the NEXT item's byte region during the
    # original full-file parse. When re-parsing standalone, the reader
    # would consume 0x00 bytes as stat_id=0 (strength) and keep reading
    # until EOF. 0xFF bytes guarantee that every 9-bit read produces
    # 0x1FF (511 = terminator), which cleanly stops the property loop.
    padded = source_data + b"\xff" * 16
    instance = D2SParser._create_reader(padded, start_byte=0)
    instance._section_end_byte = len(source_data)
    item = instance._parse_single_item()
    # The internal parser trims source_data to item_end_bit // 8 (after
    # the final byte-align), which drops any trailing inter-item padding
    # byte that belongs to this item's storage footprint. Callers pass a
    # specific blob length and MUST get that exact blob length back -
    # otherwise subsequent writes produce shorter item streams that
    # bit-shift everything downstream.
    # [BV minimal-KopieSPIEL vs KopieGUI: zhb (Set, bonus_mask=31) lost
    #  1 trailing byte -> file rejected by game]
    parsed_len = len(item.source_data) if item.source_data else 0
    input_len = len(source_data)
    if parsed_len != input_len:
        # Log WHEN truncation happens - gives early warning for new
        # edge cases (e.g. a previously-unseen item kind whose padding
        # layout differs). Callers still get the full blob back, but
        # maintainers see the discrepancy in logs.
        logger.debug(
            "parse_item_from_bytes: internal parser produced %d bytes but "
            "input was %d bytes. Restoring full input blob for '%s'. "
            "Delta=%+d (usually inter-item padding).",
            parsed_len,
            input_len,
            item.item_code,
            input_len - parsed_len,
        )
    item.source_data = bytes(source_data)
    return item


def parse_character_header(path: "Path | str") -> CharacterHeader:
    """Parse only the header of a single .d2s file.

    Reads only the first ~832 bytes of the file and decodes the
    CharacterHeader fields. Does NOT touch the Stats/Skills/Items/Merc/
    Corpse sections, does NOT instantiate a BitReader, does NOT load
    item/stat/skill databases.

    Use this when you need header info for a character-select screen
    or similar listing and want to avoid the cost of full parsing.

    Args:
        path: Path to the .d2s file.

    Returns:
        CharacterHeader with all header fields populated, including
        ``source_path`` set to the input path.

    Raises:
        FileNotFoundError:         File does not exist.
        InvalidSignatureError:     Signature != 0xAA55AA55.
        UnsupportedVersionError:   File version not supported.
        SpecVerificationError:     Stats marker 'gf' not found at 0x341.
    """
    from pathlib import Path as _Path

    p = _Path(path)

    # Only read the header bytes -- nothing more.
    with open(p, "rb") as f:
        data = f.read(HEADER_SIZE_V105 + 2)  # +2 for the 'gf' stats marker

    return _decode_header_from_bytes(data, source_path=p)


def parse_character_headers(
    save_dir: "Path | str",
    *,
    pattern: str = "*.d2s",
    skip_errors: bool = True,
) -> list[CharacterHeader]:
    """Parse only the headers of every .d2s file in a directory.

    Fast-path API for character-select screens. For each file matching
    ``pattern`` in ``save_dir``, reads only the header bytes and decodes
    the CharacterHeader. Does NOT parse Stats/Skills/Items/Mercs/Corpse.

    Only ``load_charstats()`` needs to be called before using this API.
    No item/stat/skill databases need to be loaded.

    Args:
        save_dir:    Directory to scan for .d2s files.
        pattern:     Glob pattern (default: "*.d2s").
        skip_errors: If True (default), files that fail to parse are
                     logged at WARNING level and omitted from the result.
                     If False, the first parse error is re-raised with
                     the file path in the exception context.

    Returns:
        List of CharacterHeader objects, one per successfully parsed
        file, sorted by filename. Each header has ``source_path`` set.

    Examples::

        from d2rr_toolkit.parsers.d2s_parser import parse_character_headers

        headers = parse_character_headers(save_dir)
        for h in headers:
            mark = "DEAD" if h.is_dead else "alive"
            mode = "HC" if h.is_hardcore else "SC"
            print(f"{h.character_name:20s} Lvl {h.level:3d} {h.character_class_name:12s} {mode} {mark}")
    """
    from pathlib import Path as _Path

    d = _Path(save_dir)
    if not d.is_dir():
        raise NotADirectoryError(f"Not a directory: {d}")

    results: list[CharacterHeader] = []
    files = sorted(d.glob(pattern))
    for f in files:
        if not f.is_file():
            continue
        try:
            header = parse_character_header(f)
            results.append(header)
        except Exception as e:
            if skip_errors:
                logger.warning("Skipping %s: %s", f.name, e)
                continue
            # Wrap to include file path while preserving original cause.
            # We cannot reconstruct custom exceptions (e.g. InvalidSignatureError)
            # with a new message because their __init__ has a different signature.
            raise RuntimeError(f"Failed to parse {f}: {e}") from e

    logger.info("Parsed %d character header(s) from %s", len(results), d)
    return results


def _decode_header_from_bytes(
    data: bytes,
    source_path: "Path | None" = None,
) -> CharacterHeader:
    """Decode a CharacterHeader from raw D2S header bytes.

    Shared implementation between parse_character_header() and the
    full D2SParser. All offsets [BV].

    Args:
        data: At least HEADER_SIZE_V105 + 2 bytes from the start of a .d2s.
        source_path: Optional source file path (stored on the result).

    Returns:
        CharacterHeader.

    Raises:
        InvalidSignatureError:   Signature != 0xAA55AA55.
        UnsupportedVersionError: Version not in SUPPORTED_VERSIONS.
        SpecVerificationError:   Stats marker 'gf' not found at 0x341.
    """
    # Signature
    signature = struct.unpack_from("<I", data, OFFSET_SIGNATURE)[0]
    if signature != D2S_SIGNATURE:
        raise InvalidSignatureError(signature)

    # Version
    version = struct.unpack_from("<I", data, OFFSET_VERSION)[0]
    if version not in SUPPORTED_VERSIONS:
        raise UnsupportedVersionError(version, SUPPORTED_VERSIONS)

    # File size and checksum
    file_size = struct.unpack_from("<I", data, OFFSET_FILE_SIZE)[0]
    checksum = struct.unpack_from("<I", data, OFFSET_CHECKSUM)[0]

    # Status byte at 0x14 (bit 2 = HC, bit 3 = died_flag)
    status_byte = data[OFFSET_STATUS]
    is_hardcore = bool(status_byte & 0x04)
    died_flag = bool(status_byte & 0x08)
    is_expansion = True  # Always True in D2R v105

    # Progression byte at 0x15
    progression = data[OFFSET_PROGRESSION]

    # Character class at 0x18, level at 0x1B
    char_class = data[OFFSET_CLASS]
    class_name = get_charstats_db().get_class_name(char_class)
    level = data[OFFSET_LEVEL]

    # Character name at 0x12B (null-terminated ASCII, max 16 bytes)
    name_bytes = data[OFFSET_NAME : OFFSET_NAME + 16]
    null_pos = name_bytes.find(0x00)
    if null_pos != -1:
        name = name_bytes[:null_pos].decode("ascii", errors="replace")
    else:
        name = name_bytes.decode("ascii", errors="replace")

    # Verify 'gf' stats marker at expected position (sanity check)
    if len(data) >= OFFSET_STATS_SECTION + 2:
        gf_marker = data[OFFSET_STATS_SECTION : OFFSET_STATS_SECTION + 2]
        if gf_marker != SECTION_MARKER_STATS:
            raise SpecVerificationError(
                field="stats_section_marker",
                byte_offset=OFFSET_STATS_SECTION,
                bit_offset=OFFSET_STATS_SECTION * 8,
                expected=SECTION_MARKER_STATS.hex(),
                found=gf_marker.hex(),
                context=(
                    f"Expected 'gf' at byte {OFFSET_STATS_SECTION} (v105 header size). "
                    f"File may be truncated or have an unexpected header size."
                ),
            )

    return CharacterHeader(
        version=version,
        file_size=file_size,
        checksum=checksum,
        character_name=name,
        character_class=char_class,
        character_class_name=class_name,
        level=level,
        status_byte=status_byte,
        is_hardcore=is_hardcore,
        died_flag=died_flag,
        is_expansion=is_expansion,
        progression=progression,
        source_path=source_path,
    )


# ── Quality-dispatch table population ────────────────────────────────────────
# Kept at module-tail so the class methods are defined; initialising it at
# class-definition time would require forward references. Dict values are
# unbound methods - the caller invokes them as reader_fn(self).
# _QUALITY_READERS populate block moved to d2s_parser_items.py.

