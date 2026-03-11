"""CAN frame and J1939 29-bit identifier parsing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .constants import (
    ADDRESS_NULL,
    ADDRESS_GLOBAL,
    PRIORITY_MAX,
    PDU_FORMAT_BROADCAST,
)


# ---------------------------------------------------------------------------
# J1939 ID helpers
# ---------------------------------------------------------------------------

def parse_j1939_id(can_id: int) -> tuple[int, int, int, int, int]:
    """Decompose a 29-bit J1939 extended CAN identifier.

    Returns (priority, reserved, data_page, pdu_format, pdu_specific, source_address)
    packed as (priority, pgn, source_address) – the three items callers usually
    need – PLUS the raw pf and ps for PDU-type detection.

    Returns:
        (priority, pf, ps, dp, source_address)
        where pgn can be computed from pf, ps, dp.

    Raises:
        ValueError: if can_id is not a valid 29-bit value.
    """
    if not (0 <= can_id <= 0x1FFFFFFF):
        raise ValueError(f"CAN ID 0x{can_id:X} is not a valid 29-bit value")

    source_address = can_id & 0xFF
    pdu_specific = (can_id >> 8) & 0xFF
    pdu_format = (can_id >> 16) & 0xFF
    data_page = (can_id >> 24) & 0x01
    # bit 25 is reserved (R) – ignore
    priority = (can_id >> 26) & 0x07

    return priority, pdu_format, pdu_specific, data_page, source_address


def compute_pgn(pdu_format: int, pdu_specific: int, data_page: int) -> int:
    """Compute the Parameter Group Number from PF, PS and DP fields.

    PDU1 (PF < 0xF0): PS is the destination address → not part of PGN.
    PDU2 (PF >= 0xF0): PS is the group extension → part of PGN.
    """
    if pdu_format < PDU_FORMAT_BROADCAST:
        # PDU1 – destination-specific; PS carries the destination address
        pgn = (data_page << 17) | (pdu_format << 8)
    else:
        # PDU2 – broadcast
        pgn = (data_page << 17) | (pdu_format << 8) | pdu_specific
    return pgn


def build_j1939_id(
    priority: int,
    pgn: int,
    source_address: int,
    destination_address: int = ADDRESS_GLOBAL,
) -> int:
    """Construct a 29-bit J1939 CAN identifier.

    For PDU1 PGNs (PF < 0xF0) the destination address is encoded in PS.
    For PDU2 PGNs the group extension is already embedded in the PGN.

    Args:
        priority: Message priority (0–7, where 0 is highest).
        pgn: Parameter Group Number.
        source_address: Originating ECU address (0–253).
        destination_address: Target ECU address for PDU1 messages.

    Returns:
        29-bit integer CAN ID.

    Raises:
        ValueError: On out-of-range inputs.
    """
    if not (0 <= priority <= PRIORITY_MAX):
        raise ValueError(f"Priority {priority} out of range 0–{PRIORITY_MAX}")
    if not (0 <= source_address <= 0xFF):
        raise ValueError(f"Source address 0x{source_address:X} out of range")

    data_page = (pgn >> 17) & 0x01
    pdu_format = (pgn >> 8) & 0xFF

    if pdu_format < PDU_FORMAT_BROADCAST:
        # PDU1 – embed destination address in PS field
        pdu_specific = destination_address & 0xFF
    else:
        # PDU2 – PS is already part of the PGN
        pdu_specific = pgn & 0xFF

    can_id = (
        (priority << 26)
        | (data_page << 24)
        | (pdu_format << 16)
        | (pdu_specific << 8)
        | source_address
    )
    return can_id


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CANFrame:
    """Raw CAN bus frame."""

    can_id: int
    """CAN identifier (11-bit standard or 29-bit extended)."""

    data: bytes
    """Payload bytes (0–8 bytes for classical CAN)."""

    timestamp: Optional[float] = None
    """Optional capture timestamp in seconds."""

    is_extended: bool = True
    """True when the 29-bit extended frame format is used (J1939 always uses it)."""

    interface: Optional[str] = None
    """Optional interface name (e.g. 'can0')."""

    def __post_init__(self) -> None:
        if not isinstance(self.data, (bytes, bytearray)):
            raise TypeError("data must be bytes or bytearray")
        if len(self.data) > 8:
            raise ValueError(
                f"Classical CAN payload must be ≤ 8 bytes, got {len(self.data)}"
            )
        if self.is_extended and not (0 <= self.can_id <= 0x1FFFFFFF):
            raise ValueError(
                f"Extended CAN ID 0x{self.can_id:X} is not a valid 29-bit value"
            )
        if not self.is_extended and not (0 <= self.can_id <= 0x7FF):
            raise ValueError(
                f"Standard CAN ID 0x{self.can_id:X} is not a valid 11-bit value"
            )

    @property
    def dlc(self) -> int:
        """Data Length Code – number of bytes in the payload."""
        return len(self.data)

    def hex_data(self) -> str:
        """Return payload as an uppercase hex string."""
        return self.data.hex().upper()


@dataclass
class J1939Frame:
    """Decoded J1939 message built on top of a raw CAN frame."""

    can_frame: CANFrame
    priority: int
    pgn: int
    source_address: int
    destination_address: int = ADDRESS_GLOBAL
    """Only meaningful for PDU1 messages (PF < 0xF0)."""

    @classmethod
    def from_can_frame(cls, frame: CANFrame) -> "J1939Frame":
        """Decode a :class:`CANFrame` into a :class:`J1939Frame`.

        Raises:
            ValueError: if the frame is not an extended CAN frame.
        """
        if not frame.is_extended:
            raise ValueError("J1939 requires 29-bit extended CAN frames")

        priority, pf, ps, dp, sa = parse_j1939_id(frame.can_id)
        pgn = compute_pgn(pf, ps, dp)

        if pf < PDU_FORMAT_BROADCAST:
            dest = ps  # PS encodes destination address for PDU1
        else:
            dest = ADDRESS_GLOBAL  # PDU2 messages are broadcast

        return cls(
            can_frame=frame,
            priority=priority,
            pgn=pgn,
            source_address=sa,
            destination_address=dest,
        )

    # Convenience properties -------------------------------------------------

    @property
    def data(self) -> bytes:
        return self.can_frame.data

    @property
    def timestamp(self) -> Optional[float]:
        return self.can_frame.timestamp

    @property
    def dlc(self) -> int:
        return self.can_frame.dlc

    @property
    def is_broadcast(self) -> bool:
        """True for PDU2 (broadcast) messages."""
        pf = (self.can_frame.can_id >> 16) & 0xFF
        return pf >= PDU_FORMAT_BROADCAST

    @property
    def is_global_destination(self) -> bool:
        return self.destination_address == ADDRESS_GLOBAL

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"J1939Frame(pgn=0x{self.pgn:04X}({self.pgn}), "
            f"priority={self.priority}, "
            f"src=0x{self.source_address:02X}, "
            f"dst=0x{self.destination_address:02X}, "
            f"data={self.can_frame.hex_data()})"
        )
