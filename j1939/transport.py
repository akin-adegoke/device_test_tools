"""J1939 Transport Protocol (TP) – BAM and CMDT session handling.

J1939 uses two TP mechanisms for payloads larger than 8 bytes:

* **BAM (Broadcast Announce Message)** – one-to-many, no flow-control.
* **CMDT (Connection Mode Data Transfer)** – one-to-one, with flow-control.

Both use PGN_TP_CM (0xEC00) for connection management and PGN_TP_DT (0xEB00)
for the actual data packets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, List

from .constants import (
    ADDRESS_GLOBAL,
    PGN_TP_CM,
    PGN_TP_DT,
    TP_CM_BAM,
    TP_CM_RTS,
    TP_CM_CTS,
    TP_CM_EOMACK,
    TP_CM_CONNABORT,
)
from .frame import J1939Frame


# ---------------------------------------------------------------------------
# Session key: (source_address, destination_address, pgn)
# ---------------------------------------------------------------------------
SessionKey = tuple[int, int, int]


@dataclass
class TPSession:
    """Tracks the assembly state for a single TP message."""

    source_address: int
    destination_address: int
    pgn: int
    total_message_size: int
    total_packets: int
    is_bam: bool

    received_packets: Dict[int, bytes] = field(default_factory=dict)
    """Mapping of sequence_number (1-based) → 7-byte data payload."""

    @property
    def is_complete(self) -> bool:
        return len(self.received_packets) == self.total_packets

    def add_data_packet(self, sequence_number: int, data: bytes) -> None:
        """Store a TP.DT data packet (7 usable bytes after seq byte)."""
        if not (1 <= sequence_number <= 255):
            raise ValueError(f"Invalid TP.DT sequence number {sequence_number}")
        self.received_packets[sequence_number] = data

    def reassemble(self) -> bytes:
        """Concatenate all received data packets in order and trim to size.

        Raises:
            RuntimeError: if the session is not yet complete.
        """
        if not self.is_complete:
            raise RuntimeError(
                f"TP session for PGN 0x{self.pgn:04X} not yet complete: "
                f"{len(self.received_packets)}/{self.total_packets} packets received"
            )
        payload = bytearray()
        for seq in range(1, self.total_packets + 1):
            payload.extend(self.received_packets[seq])
        return bytes(payload[: self.total_message_size])


@dataclass
class TPResult:
    """Result produced when a TP session completes."""

    pgn: int
    source_address: int
    destination_address: int
    data: bytes


class TransportProtocolHandler:
    """Stateful handler that reassembles multi-packet J1939 TP messages.

    Usage::

        handler = TransportProtocolHandler()
        for frame in j1939_frames:
            result = handler.process(frame)
            if result is not None:
                # A complete multi-packet message was reassembled
                print(result.pgn, result.data)
    """

    def __init__(self) -> None:
        self._sessions: Dict[SessionKey, TPSession] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: J1939Frame) -> Optional[TPResult]:
        """Process a J1939 frame and return a :class:`TPResult` when a
        complete multi-packet message has been reassembled.

        Returns ``None`` for non-TP frames and incomplete sessions.
        """
        if frame.pgn == PGN_TP_CM:
            return self._handle_tp_cm(frame)
        if frame.pgn == PGN_TP_DT:
            return self._handle_tp_dt(frame)
        return None

    def active_sessions(self) -> List[SessionKey]:
        """Return a list of currently active (incomplete) session keys."""
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_tp_cm(self, frame: J1939Frame) -> Optional[TPResult]:
        data = frame.data
        if len(data) < 8:
            return None

        control = data[0]
        sa = frame.source_address
        da = frame.destination_address

        if control == TP_CM_BAM:
            total_size = int.from_bytes(data[1:3], "little")
            total_packets = data[3]
            pgn = int.from_bytes(data[5:8], "little") & 0x3FFFF
            key: SessionKey = (sa, ADDRESS_GLOBAL, pgn)
            self._sessions[key] = TPSession(
                source_address=sa,
                destination_address=ADDRESS_GLOBAL,
                pgn=pgn,
                total_message_size=total_size,
                total_packets=total_packets,
                is_bam=True,
            )

        elif control == TP_CM_RTS:
            total_size = int.from_bytes(data[1:3], "little")
            total_packets = data[3]
            pgn = int.from_bytes(data[5:8], "little") & 0x3FFFF
            key = (sa, da, pgn)
            self._sessions[key] = TPSession(
                source_address=sa,
                destination_address=da,
                pgn=pgn,
                total_message_size=total_size,
                total_packets=total_packets,
                is_bam=False,
            )

        elif control == TP_CM_CONNABORT:
            # Clean up any matching session
            pgn = int.from_bytes(data[5:8], "little") & 0x3FFFF
            self._sessions.pop((sa, da, pgn), None)

        return None

    def _handle_tp_dt(self, frame: J1939Frame) -> Optional[TPResult]:
        data = frame.data
        if len(data) < 8:
            return None

        seq = data[0]
        payload = bytes(data[1:8])
        sa = frame.source_address
        da = frame.destination_address

        # Try to match an active session (BAM uses ADDRESS_GLOBAL as dest)
        session = self._sessions.get((sa, da, 0))  # placeholder lookup
        for key, sess in list(self._sessions.items()):
            if key[0] == sa and (key[1] == da or key[1] == ADDRESS_GLOBAL):
                session = sess
                break

        if session is None:
            return None  # No matching session; ignore orphan packet

        session.add_data_packet(seq, payload)

        if session.is_complete:
            key = (session.source_address, session.destination_address, session.pgn)
            self._sessions.pop(key, None)
            return TPResult(
                pgn=session.pgn,
                source_address=session.source_address,
                destination_address=session.destination_address,
                data=session.reassemble(),
            )

        return None
