"""SPN (Suspect Parameter Number) signal extraction and scaling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import (
    SPN_DEFINITIONS,
    SPN_ERROR_INDICATOR_1BYTE,
    SPN_NOT_AVAILABLE_1BYTE,
    SPN_ERROR_INDICATOR_2BYTE,
    SPN_NOT_AVAILABLE_2BYTE,
    SPN_ERROR_INDICATOR_4BYTE,
    SPN_NOT_AVAILABLE_4BYTE,
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SPNValue:
    """The decoded engineering value for a single SPN."""

    spn: int
    name: str
    raw_value: int
    """Raw integer value extracted from the payload bits."""

    engineering_value: Optional[float]
    """Scaled value in engineering units; ``None`` when not available or error."""

    unit: str
    is_error: bool = False
    is_not_available: bool = False

    def __repr__(self) -> str:  # pragma: no cover
        if self.is_not_available:
            return f"SPNValue(spn={self.spn}, name={self.name!r}, N/A)"
        if self.is_error:
            return f"SPNValue(spn={self.spn}, name={self.name!r}, ERROR)"
        return (
            f"SPNValue(spn={self.spn}, name={self.name!r}, "
            f"value={self.engineering_value} {self.unit})"
        )


# ---------------------------------------------------------------------------
# Error / not-available thresholds per bit-length
# ---------------------------------------------------------------------------

_NA_THRESHOLDS = {
    1:  (None, 1),
    2:  (None, 3),
    4:  (0xE, 0xF),
    8:  (SPN_ERROR_INDICATOR_1BYTE, SPN_NOT_AVAILABLE_1BYTE),
    16: (SPN_ERROR_INDICATOR_2BYTE, SPN_NOT_AVAILABLE_2BYTE),
    32: (SPN_ERROR_INDICATOR_4BYTE, SPN_NOT_AVAILABLE_4BYTE),
}


def _is_error(raw: int, length_bits: int) -> bool:
    thresholds = _NA_THRESHOLDS.get(length_bits)
    if thresholds and thresholds[0] is not None:
        return raw == thresholds[0]
    return False


def _is_not_available(raw: int, length_bits: int) -> bool:
    thresholds = _NA_THRESHOLDS.get(length_bits)
    if thresholds and thresholds[1] is not None:
        return raw == thresholds[1]
    return False


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_bits(data: bytes, byte_offset: int, bit_offset: int, length_bits: int) -> int:
    """Extract *length_bits* bits from *data* starting at
    *byte_offset* byte and *bit_offset* within that byte (LSB = 0).

    J1939 signals are stored little-endian (Intel byte order) by default.

    Args:
        data: Payload bytes.
        byte_offset: 0-based start byte.
        bit_offset: 0-based bit offset within the start byte (0 = LSB).
        length_bits: Number of bits to extract.

    Returns:
        Unsigned integer raw value.

    Raises:
        IndexError: if the requested bits extend beyond the data buffer.
    """
    # Build a combined integer from relevant bytes (little-endian)
    total_bits_needed = bit_offset + length_bits
    total_bytes_needed = (total_bits_needed + 7) // 8
    if byte_offset + total_bytes_needed > len(data):
        raise IndexError(
            f"Payload too short: need byte {byte_offset + total_bytes_needed - 1}, "
            f"have {len(data)} bytes"
        )

    value = 0
    for i in range(total_bytes_needed):
        value |= data[byte_offset + i] << (i * 8)

    # Shift and mask
    value >>= bit_offset
    mask = (1 << length_bits) - 1
    return value & mask


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decode_spn(spn: int, data: bytes) -> SPNValue:
    """Decode a single SPN from a J1939 payload.

    Args:
        spn: SPN number.
        data: 8-byte (or longer) payload.

    Returns:
        :class:`SPNValue` containing the decoded engineering value.

    Raises:
        KeyError: if *spn* is not in the built-in SPN database.
        IndexError: if *data* is too short for the SPN.
    """
    defn = SPN_DEFINITIONS.get(spn)
    if defn is None:
        raise KeyError(f"SPN {spn} not found in the built-in SPN database")

    raw = extract_bits(
        data,
        defn["byte_offset"],
        defn["bit_offset"],
        defn["length_bits"],
    )

    is_err = _is_error(raw, defn["length_bits"])
    is_na = _is_not_available(raw, defn["length_bits"])

    if is_err or is_na:
        eng = None
    else:
        eng = raw * defn["scale"] + defn["offset"]

    return SPNValue(
        spn=spn,
        name=defn["name"],
        raw_value=raw,
        engineering_value=eng,
        unit=defn["unit"],
        is_error=is_err,
        is_not_available=is_na,
    )


def get_spn_definition(spn: int) -> Optional[dict]:
    """Return the raw SPN definition dictionary, or ``None`` if unknown."""
    return SPN_DEFINITIONS.get(spn)


def list_spns_for_pgn(pgn: int) -> list[int]:
    """Return a list of SPN numbers associated with *pgn*."""
    return [
        spn
        for spn, defn in SPN_DEFINITIONS.items()
        if defn["pgn"] == pgn
    ]


def is_in_operational_range(value: SPNValue) -> bool:
    """Return ``True`` when the engineering value is within the defined range.

    Returns ``False`` for error/not-available values and out-of-range values.
    """
    if value.is_error or value.is_not_available or value.engineering_value is None:
        return False
    defn = SPN_DEFINITIONS.get(value.spn)
    if defn is None:
        return False
    return defn["range_min"] <= value.engineering_value <= defn["range_max"]
