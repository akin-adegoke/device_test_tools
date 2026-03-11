"""Tests for the J1939 Transport Protocol (TP) handler."""
from __future__ import annotations

import pytest

from j1939.frame import CANFrame, J1939Frame, build_j1939_id
from j1939.transport import TransportProtocolHandler, TPSession
from j1939.constants import (
    ADDRESS_GLOBAL,
    PGN_TP_CM,
    PGN_TP_DT,
    PGN_DM1,
    TP_CM_BAM,
    TP_CM_RTS,
    TP_CM_CONNABORT,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_tp_cm_bam(source: int, pgn: int, total_size: int, num_packets: int) -> J1939Frame:
    """Build a TP.CM BAM frame."""
    can_id = build_j1939_id(7, PGN_TP_CM, source, ADDRESS_GLOBAL)
    pgn_bytes = pgn.to_bytes(3, "little")
    data = bytes([TP_CM_BAM, total_size & 0xFF, (total_size >> 8) & 0xFF,
                  num_packets, 0xFF]) + pgn_bytes
    raw = CANFrame(can_id=can_id, data=data, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(raw)


def _make_tp_dt(source: int, dest: int, seq: int, payload: bytes) -> J1939Frame:
    """Build a TP.DT frame; payload must be exactly 7 bytes."""
    assert len(payload) == 7, "TP.DT payload is always 7 bytes"
    can_id = build_j1939_id(7, PGN_TP_DT, source, dest)
    data = bytes([seq]) + payload
    raw = CANFrame(can_id=can_id, data=data, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(raw)


def _make_tp_cm_rts(source: int, dest: int, pgn: int,
                    total_size: int, num_packets: int) -> J1939Frame:
    """Build a TP.CM_RTS (connection-mode Request-to-Send) frame."""
    can_id = build_j1939_id(7, PGN_TP_CM, source, dest)
    pgn_bytes = pgn.to_bytes(3, "little")
    data = bytes([TP_CM_RTS, total_size & 0xFF, (total_size >> 8) & 0xFF,
                  num_packets, 0xFF]) + pgn_bytes
    raw = CANFrame(can_id=can_id, data=data, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(raw)


def _make_tp_cm_abort(source: int, dest: int, pgn: int) -> J1939Frame:
    """Build a TP.CM_CONNABORT frame."""
    can_id = build_j1939_id(7, PGN_TP_CM, source, dest)
    pgn_bytes = pgn.to_bytes(3, "little")
    data = bytes([TP_CM_CONNABORT, 0xFF, 0xFF, 0xFF, 0xFF]) + pgn_bytes
    raw = CANFrame(can_id=can_id, data=data, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(raw)


# ---------------------------------------------------------------------------
# TPSession unit tests
# ---------------------------------------------------------------------------

class TestTPSession:

    def test_not_complete_when_no_packets(self):
        session = TPSession(
            source_address=0x01,
            destination_address=ADDRESS_GLOBAL,
            pgn=PGN_DM1,
            total_message_size=14,
            total_packets=2,
            is_bam=True,
        )
        assert not session.is_complete

    def test_complete_when_all_packets_received(self):
        session = TPSession(
            source_address=0x01,
            destination_address=ADDRESS_GLOBAL,
            pgn=PGN_DM1,
            total_message_size=14,
            total_packets=2,
            is_bam=True,
        )
        session.add_data_packet(1, bytes(7))
        session.add_data_packet(2, bytes(7))
        assert session.is_complete

    def test_reassemble_trims_to_declared_size(self):
        session = TPSession(
            source_address=0x01,
            destination_address=ADDRESS_GLOBAL,
            pgn=PGN_DM1,
            total_message_size=10,  # only 10 of 14 bytes used
            total_packets=2,
            is_bam=True,
        )
        session.add_data_packet(1, bytes([0x01] * 7))
        session.add_data_packet(2, bytes([0x02] * 7))
        result = session.reassemble()
        assert len(result) == 10
        assert result == bytes([0x01] * 7 + [0x02] * 3)

    def test_reassemble_raises_when_incomplete(self):
        session = TPSession(
            source_address=0x01,
            destination_address=ADDRESS_GLOBAL,
            pgn=PGN_DM1,
            total_message_size=14,
            total_packets=2,
            is_bam=True,
        )
        session.add_data_packet(1, bytes(7))
        with pytest.raises(RuntimeError, match="not yet complete"):
            session.reassemble()

    def test_invalid_sequence_number_raises(self):
        session = TPSession(
            source_address=0x01,
            destination_address=ADDRESS_GLOBAL,
            pgn=PGN_DM1,
            total_message_size=7,
            total_packets=1,
            is_bam=True,
        )
        with pytest.raises(ValueError, match="sequence number"):
            session.add_data_packet(0, bytes(7))  # seq must be >= 1


# ---------------------------------------------------------------------------
# TransportProtocolHandler – BAM
# ---------------------------------------------------------------------------

class TestBAMReassembly:
    """End-to-end BAM (broadcast) TP reassembly."""

    def test_three_packet_bam_reassembly(self):
        handler = TransportProtocolHandler()

        announce = _make_tp_cm_bam(0x01, PGN_DM1, 20, 3)
        assert handler.process(announce) is None

        assert len(handler.active_sessions()) == 1

        dt1 = _make_tp_dt(0x01, ADDRESS_GLOBAL, 1, bytes(range(1, 8)))
        dt2 = _make_tp_dt(0x01, ADDRESS_GLOBAL, 2, bytes(range(8, 15)))
        dt3 = _make_tp_dt(0x01, ADDRESS_GLOBAL, 3, bytes(range(15, 22)))

        assert handler.process(dt1) is None
        assert handler.process(dt2) is None
        result = handler.process(dt3)

        assert result is not None
        assert result.pgn == PGN_DM1
        assert result.source_address == 0x01
        assert len(result.data) == 20

        # Verify content: first 7 bytes = [1..7], next 7 = [8..14], remaining 6 = [15..20]
        expected = bytes(range(1, 21))
        assert result.data == expected

    def test_single_packet_bam(self):
        handler = TransportProtocolHandler()
        announce = _make_tp_cm_bam(0x02, PGN_DM1, 5, 1)
        handler.process(announce)
        dt1 = _make_tp_dt(0x02, ADDRESS_GLOBAL, 1, bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11]))
        result = handler.process(dt1)
        assert result is not None
        assert result.data == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE])  # trimmed to 5

    def test_no_active_sessions_after_completion(self):
        handler = TransportProtocolHandler()
        announce = _make_tp_cm_bam(0x03, PGN_DM1, 7, 1)
        handler.process(announce)
        dt1 = _make_tp_dt(0x03, ADDRESS_GLOBAL, 1, bytes(7))
        handler.process(dt1)
        assert len(handler.active_sessions()) == 0

    def test_orphan_dt_without_bam_ignored(self):
        """TP.DT with no matching session should be silently ignored."""
        handler = TransportProtocolHandler()
        dt = _make_tp_dt(0x99, ADDRESS_GLOBAL, 1, bytes(7))
        result = handler.process(dt)
        assert result is None

    def test_non_tp_frame_returns_none(self):
        from j1939.constants import PGN_EEC1
        handler = TransportProtocolHandler()
        can_id = build_j1939_id(6, PGN_EEC1, 0x00)
        raw = CANFrame(can_id=can_id, data=bytes(8), is_extended=True, interface="vcan0")
        frame = J1939Frame.from_can_frame(raw)
        assert handler.process(frame) is None


# ---------------------------------------------------------------------------
# TransportProtocolHandler – Connection Mode (RTS/CTS)
# ---------------------------------------------------------------------------

class TestConnectionModeTP:

    def test_rts_creates_session(self):
        handler = TransportProtocolHandler()
        rts = _make_tp_cm_rts(0x01, 0x02, PGN_DM1, 14, 2)
        handler.process(rts)
        assert len(handler.active_sessions()) == 1

    def test_connection_abort_removes_session(self):
        handler = TransportProtocolHandler()
        rts = _make_tp_cm_rts(0x01, 0x02, PGN_DM1, 14, 2)
        handler.process(rts)
        abort = _make_tp_cm_abort(0x01, 0x02, PGN_DM1)
        handler.process(abort)
        assert len(handler.active_sessions()) == 0

    def test_rts_then_dt_reassembly(self):
        handler = TransportProtocolHandler()
        rts = _make_tp_cm_rts(0x01, 0x02, PGN_DM1, 9, 2)
        handler.process(rts)

        dt1 = _make_tp_dt(0x01, 0x02, 1, bytes([0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16]))
        dt2 = _make_tp_dt(0x01, 0x02, 2, bytes([0x20, 0x21, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]))

        assert handler.process(dt1) is None
        result = handler.process(dt2)

        assert result is not None
        assert len(result.data) == 9
        assert result.data[:7] == bytes([0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16])
        assert result.data[7:9] == bytes([0x20, 0x21])
