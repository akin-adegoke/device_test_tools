"""PGN (Parameter Group Number) utilities and database lookup."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import (
    PDU_FORMAT_BROADCAST,
    PGN_INFO,
)


@dataclass
class PGNInfo:
    """Metadata about a known PGN."""

    pgn: int
    name: str
    expected_length: int
    """Expected data length in bytes; -1 means variable."""


def get_pgn_info(pgn: int) -> Optional[PGNInfo]:
    """Return :class:`PGNInfo` for a known PGN, or ``None`` if unknown.

    Args:
        pgn: Parameter Group Number.

    Returns:
        :class:`PGNInfo` instance, or ``None`` for unknown PGNs.
    """
    entry = PGN_INFO.get(pgn)
    if entry is None:
        return None
    name, length = entry
    return PGNInfo(pgn=pgn, name=name, expected_length=length)


def is_pdu1(pgn: int) -> bool:
    """Return ``True`` when *pgn* uses PDU1 (peer-to-peer) format.

    PDU1: PF byte < 0xF0 (240).
    """
    pf = (pgn >> 8) & 0xFF
    return pf < PDU_FORMAT_BROADCAST


def is_pdu2(pgn: int) -> bool:
    """Return ``True`` when *pgn* uses PDU2 (broadcast) format.

    PDU2: PF byte >= 0xF0 (240).
    """
    return not is_pdu1(pgn)


def is_valid_pgn(pgn: int) -> bool:
    """Check that a PGN value is within the 18-bit addressable range.

    The J1939 PGN is an 18-bit value (DP[1] | PF[8] | PS[8] for PDU2,
    or DP[1] | PF[8] for PDU1 with PS set to 0).

    Args:
        pgn: Parameter Group Number.

    Returns:
        ``True`` if the PGN fits in 18 bits (0–0x3FFFF).
    """
    return 0 <= pgn <= 0x3FFFF


def pgn_to_description(pgn: int) -> str:
    """Return a human-readable description for *pgn*.

    Falls back to a generic hex-formatted string for unknown PGNs.
    """
    info = get_pgn_info(pgn)
    if info:
        return f"{info.name} (PGN 0x{pgn:04X})"
    return f"Unknown PGN 0x{pgn:04X} ({pgn})"
