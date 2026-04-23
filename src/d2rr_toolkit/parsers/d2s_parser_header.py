"""D2S header parser - mixin extracted from D2SParser.

Hosts the 85-LOC ``_parse_header`` method previously inlined in the
monolithic parser. Kept as a mixin (vs a free-standing class) so
downstream state access (``self._reader``, ``self._data``,
``self._path``) stays identical to the pre-refactor implementation -
byte-exact golden diff is the safety gate (see
``tests/test_d2s_parse_snapshot.py``).

All [BV] / [BINARY_VERIFIED] tags moved verbatim with the code.
"""

from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING

from d2rr_toolkit.constants import (
    D2S_SIGNATURE,
    OFFSET_CHECKSUM,
    OFFSET_CLASS,
    OFFSET_FILE_SIZE,
    OFFSET_LEVEL,
    OFFSET_NAME,
    OFFSET_PROGRESSION,
    OFFSET_SIGNATURE,
    OFFSET_STATS_SECTION,
    OFFSET_STATUS,
    OFFSET_VERSION,
    SECTION_MARKER_STATS,
    SUPPORTED_VERSIONS,
)
from d2rr_toolkit.exceptions import (
    InvalidSignatureError,
    SpecVerificationError,
    UnsupportedVersionError,
)
from d2rr_toolkit.game_data.charstats import get_charstats_db
from d2rr_toolkit.models.character import CharacterHeader

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from d2rr_toolkit.parsers.bit_reader import BitReader

logger = logging.getLogger(__name__)


class HeaderParserMixin:
    """Mixin providing ``_parse_header`` for :class:`D2SParser`.

    Relies on three parser-owned attributes populated by the main
    parser's ``__init__`` / ``parse`` entry point:

      * ``self._data: bytes``        - the raw file bytes
      * ``self._reader: BitReader``  - the bit-level reader
      * ``self._path: Path``         - original save-file path (for
                                       provenance on CharacterHeader)

    Does not introduce any new state. Type-only references to
    ``BitReader`` / ``Path`` live under ``TYPE_CHECKING``.
    """

    # Forward-declare the attributes the mixin reads so mypy doesn't
    # complain when the mixin is type-checked in isolation. The real
    # instances get these from ``D2SParser.__init__``.
    _data: bytes
    _reader: "BitReader | None"
    _path: "Path"
    _require_reader: "Callable[[], BitReader]"

    def _parse_header(self) -> CharacterHeader:
        """Parse the D2S file header.

        All offsets [BV] for v105. See VERIFICATION_LOG.md.

        Returns:
            CharacterHeader with all fields populated.

        Raises:
            InvalidSignatureError:   Signature != 0xAA55AA55.
            UnsupportedVersionError: Version not in SUPPORTED_VERSIONS.
        """
        reader = self._require_reader()
        data = self._data

        # Signature [BV]
        signature = struct.unpack_from("<I", data, OFFSET_SIGNATURE)[0]
        if signature != D2S_SIGNATURE:
            raise InvalidSignatureError(signature)

        # Version [BV]
        version = struct.unpack_from("<I", data, OFFSET_VERSION)[0]
        if version not in SUPPORTED_VERSIONS:
            raise UnsupportedVersionError(version, SUPPORTED_VERSIONS)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("D2S version: %d", version)

        # File size and checksum [BV]
        file_size = struct.unpack_from("<I", data, OFFSET_FILE_SIZE)[0]
        checksum = struct.unpack_from("<I", data, OFFSET_CHECKSUM)[0]

        # Character status [BV HCLives/HCDied/5 SC chars] - offset 0x14
        # Bit layout in D2R v105:
        #   bit 2 (0x04): Hardcore
        #   bit 3 (0x08): Died flag (HC=permadead, SC=historical)
        # Expansion is implicit in D2R (always True).
        status_byte = data[OFFSET_STATUS]
        is_hardcore = bool(status_byte & 0x04)
        died_flag = bool(status_byte & 0x08)
        is_expansion = True  # D2R is always Expansion

        # Character progression [BV] - offset 0x15
        # 0=no title, 5=Normal, 10=Nightmare, 15=Hell completed
        progression = data[OFFSET_PROGRESSION]

        # Character class [BV] - offset 0x18
        char_class = data[OFFSET_CLASS]
        class_name = get_charstats_db().get_class_name(char_class)

        # Character level [BV] - offset 0x1B
        level = data[OFFSET_LEVEL]

        # Character name [BV] - offset 0x12B, null-terminated ASCII
        name_bytes = data[OFFSET_NAME:]
        null_pos = name_bytes.find(0x00)
        name = (
            name_bytes[:null_pos].decode("ascii")
            if null_pos != -1
            else name_bytes[:16].decode("ascii", errors="replace")
        )

        # Verify 'gf' stats marker at expected position [BV]
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
                    f"If this fails, the header size assumption is wrong. "
                    f"Run tests/verification/verify_header.py to investigate."
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
            died_flag=died_flag,
            is_hardcore=is_hardcore,
            is_expansion=is_expansion,
            progression=progression,
            source_path=self._path,
        )

