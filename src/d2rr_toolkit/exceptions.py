"""Custom exceptions for the D2RR Toolkit D2S parser.

Every exception carries enough context to understand exactly what went wrong
and at which byte/bit offset -- critical for debugging binary format issues.
"""


class ToolkitError(Exception):
    """Base exception for all D2RR Toolkit errors."""


class D2SWriteError(ToolkitError):
    """Raised on any writer-path invariant violation (D2S or D2I).

    Covers programmer-invariant failures that were previously guarded
    by ``assert`` statements - kept reachable under ``python -O`` where
    asserts are stripped.  Also raised for Section 5 / carry1 conflicts
    that would corrupt the output file.

    The name is a historical anchor (``D2SWriteError`` - the D2S writer
    was the first consumer); the D2I writer also imports this type.
    """


class ConfigurationError(ToolkitError):
    """Raised when required game paths cannot be resolved.

    Fired by :func:`d2rr_toolkit.config.init_game_paths` when neither
    the caller nor the ``D2RR_D2R_INSTALL`` / ``D2RR_MOD_DIR`` env
    vars supply a path and no plausible OS-specific default exists
    (e.g. on POSIX where the Windows install heuristic does not apply).
    """


class InvalidFileError(ToolkitError):
    """Raised when the file is not a valid D2S save file."""


class UnsupportedVersionError(ToolkitError):
    """Raised when the D2S version is not supported by this parser.

    The parser only fully supports version 105 (D2R Reimagined).
    """

    def __init__(self, found_version: int, supported_versions: tuple[int, ...]) -> None:
        self.found_version = found_version
        self.supported_versions = supported_versions
        super().__init__(
            f"Unsupported D2S version: {found_version}. "
            f"Supported: {supported_versions}. "
            f"This parser targets D2R Reimagined (v105)."
        )


class InvalidSignatureError(ToolkitError):
    """Raised when the magic signature bytes do not match 0xAA55AA55.

    [BV] Expected signature: 0xAA55AA55
    """

    def __init__(self, found: int) -> None:
        self.found = found
        super().__init__(
            f"Invalid D2S signature: 0x{found:08X}. "
            f"Expected: 0xAA55AA55. "
            f"File may be corrupted or not a D2S save."
        )


class SpecVerificationError(ToolkitError):
    """Raised when a [SPEC_ONLY] assumption is contradicted by binary data.

    This error means we encountered binary data that does not match what
    the spec (or a [SPEC_ONLY] assumption) predicted. The parser cannot
    safely continue without resolving this discrepancy.

    When this error occurs:
    1. Run the relevant verification script from tests/verification/
    2. Document the finding in VERIFICATION_LOG.md
    3. Update the parser with the correct value
    4. Tag the finding as [BV]
    """

    def __init__(
        self,
        field: str,
        byte_offset: int,
        bit_offset: int,
        expected: object,
        found: object,
        context: str = "",
    ) -> None:
        self.field = field
        self.byte_offset = byte_offset
        self.bit_offset = bit_offset
        self.expected = expected
        self.found = found
        msg = (
            f"[SPEC_ONLY] assumption violated for field '{field}': "
            f"expected {expected!r}, found {found!r} "
            f"at byte 0x{byte_offset:04X} ({byte_offset}d), "
            f"bit {bit_offset}."
        )
        if context:
            msg += f" Context: {context}"
        super().__init__(msg)


class BitReaderError(ToolkitError):
    """Raised when the BitReader encounters an unrecoverable error."""

    def __init__(self, message: str, bit_position: int) -> None:
        self.bit_position = bit_position
        super().__init__(
            f"BitReader error at bit {bit_position} (byte {bit_position // 8}): {message}"
        )


class HuffmanDecodeError(ToolkitError):
    """Raised when Huffman item code decoding fails.

    [BV] Huffman decoding starts at item-relative bit 53.
    """

    def __init__(self, bit_position: int, bits_consumed: int) -> None:
        self.bit_position = bit_position
        self.bits_consumed = bits_consumed
        super().__init__(
            f"Huffman decode failed at absolute bit {bit_position} "
            f"after consuming {bits_consumed} bits. "
            f"Item code table may be incomplete or data is corrupted."
        )

