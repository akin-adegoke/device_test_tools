"""Tests for CAN frame parsing and J1939 ID decomposition."""
from __future__ import annotations

import pytest

from j1939.frame import (
    CANFrame,
    J1939Frame,
    parse_j1939_id,
    compute_pgn,
    build_j1939_id,
)
from j1939.constants import (
    ADDRESS_GLOBAL,
    PDU_FORMAT_BROADCAST,
    PGN_EEC1,
    PGN_CCVS1,
    PGN_ADDRESS_CLAIMED,
    PGN_TP_CM,
)


# ---------------------------------------------------------------------------
# parse_j1939_id
# ---------------------------------------------------------------------------

class TestParseJ1939ID:
    """Unit tests for parse_j1939_id()."""

    def test_eec1_engine_controller(self):
        """EEC1: CAN ID = 0x18F00400 → priority=6, PF=0xF0, PS=0x04, DP=0, SA=0x00."""
        priority, pf, ps, dp, sa = parse_j1939_id(0x18F00400)
        assert priority == 6
        assert pf == 0xF0
        assert ps == 0x04
        assert dp == 0
        assert sa == 0x00

    def test_ccvs1_vehicle_speed(self):
        """CCVS1: CAN ID = 0x18FEF100 → priority=6, PF=0xFE, PS=0xF1, DP=0, SA=0x00."""
        priority, pf, ps, dp, sa = parse_j1939_id(0x18FEF100)
        assert priority == 6
        assert pf == 0xFE
        assert ps == 0xF1
        assert dp == 0
        assert sa == 0x00

    def test_priority_7_highest_urgency(self):
        """Priority field extraction for value 7 (reserved/highest urgency)."""
        # Build an ID with priority=7
        can_id = (7 << 26) | (0xF0 << 16) | (0x04 << 8) | 0x01
        priority, *_ = parse_j1939_id(can_id)
        assert priority == 7

    def test_priority_0_lowest_urgency(self):
        """Priority field extraction for value 0."""
        can_id = (0 << 26) | (0xF0 << 16) | (0x04 << 8) | 0x01
        priority, *_ = parse_j1939_id(can_id)
        assert priority == 0

    def test_data_page_bit_set(self):
        """Data Page (DP) bit extraction when set."""
        can_id = (6 << 26) | (1 << 24) | (0xF0 << 16) | (0x04 << 8) | 0x01
        _, pf, ps, dp, sa = parse_j1939_id(can_id)
        assert dp == 1

    def test_source_address_255_broadcast_source(self):
        """Source address = 0xFF is technically invalid but parseable."""
        can_id = (6 << 26) | (0xFE << 16) | (0xF1 << 8) | 0xFF
        _, _, _, _, sa = parse_j1939_id(can_id)
        assert sa == 0xFF

    def test_invalid_id_exceeds_29_bits(self):
        """IDs larger than 29 bits should raise ValueError."""
        with pytest.raises(ValueError, match="29-bit"):
            parse_j1939_id(0x20000000)

    def test_minimum_valid_id(self):
        """ID = 0 is a valid minimum."""
        priority, pf, ps, dp, sa = parse_j1939_id(0)
        assert priority == 0
        assert pf == 0
        assert ps == 0
        assert dp == 0
        assert sa == 0

    def test_maximum_valid_id(self):
        """ID = 0x1FFFFFFF is the maximum 29-bit value."""
        priority, pf, ps, dp, sa = parse_j1939_id(0x1FFFFFFF)
        assert priority == 7
        assert pf == 0xFF
        assert ps == 0xFF
        assert dp == 1
        assert sa == 0xFF

    def test_negative_id_raises(self):
        with pytest.raises(ValueError):
            parse_j1939_id(-1)


# ---------------------------------------------------------------------------
# compute_pgn
# ---------------------------------------------------------------------------

class TestComputePGN:
    """Tests for PGN calculation from PF / PS / DP fields."""

    def test_pdu1_pgn_excludes_ps(self):
        """PDU1 (PF < 0xF0): PS is destination, not part of PGN."""
        # PGN_TP_CM = 0xEC00; PF=0xEC (236 < 240), PS=0xFF (global dest)
        pgn = compute_pgn(0xEC, 0xFF, 0)
        assert pgn == 0xEC00

    def test_pdu2_pgn_includes_ps(self):
        """PDU2 (PF >= 0xF0): PS (group extension) is part of PGN."""
        # CCVS1 PGN = 0xFEF1; PF=0xFE, PS=0xF1
        pgn = compute_pgn(0xFE, 0xF1, 0)
        assert pgn == 0xFEF1

    def test_eec1_pgn(self):
        """EEC1 PGN = 0xF004; PF=0xF0 (>=240), PS=0x04."""
        pgn = compute_pgn(0xF0, 0x04, 0)
        assert pgn == PGN_EEC1

    def test_data_page_1_shifts_pgn(self):
        """DP=1 shifts the PGN into the second data page."""
        pgn_dp0 = compute_pgn(0xF0, 0x04, 0)
        pgn_dp1 = compute_pgn(0xF0, 0x04, 1)
        assert pgn_dp1 == pgn_dp0 | (1 << 17)

    def test_pdu1_boundary_pf_239(self):
        """PF = 239 (0xEF) is still PDU1."""
        pgn = compute_pgn(0xEF, 0xAB, 0)
        assert pgn == 0xEF00  # PS not included

    def test_pdu2_boundary_pf_240(self):
        """PF = 240 (0xF0) is PDU2."""
        pgn = compute_pgn(0xF0, 0xAB, 0)
        assert pgn == 0xF0AB  # PS included


# ---------------------------------------------------------------------------
# build_j1939_id
# ---------------------------------------------------------------------------

class TestBuildJ1939ID:
    """Tests for build_j1939_id() round-trip and edge cases."""

    def test_round_trip_pdu2_broadcast(self):
        """Build an ID for a PDU2 PGN and parse it back."""
        can_id = build_j1939_id(priority=6, pgn=PGN_CCVS1, source_address=0x00)
        priority, pf, ps, dp, sa = parse_j1939_id(can_id)
        pgn = compute_pgn(pf, ps, dp)
        assert priority == 6
        assert pgn == PGN_CCVS1
        assert sa == 0x00

    def test_round_trip_pdu1_peer_to_peer(self):
        """Build a PDU1 ID with a specific destination and verify."""
        can_id = build_j1939_id(
            priority=6, pgn=PGN_TP_CM, source_address=0x01, destination_address=0x02
        )
        priority, pf, ps, dp, sa = parse_j1939_id(can_id)
        assert priority == 6
        assert sa == 0x01
        assert ps == 0x02  # PS encodes destination for PDU1

    def test_result_is_valid_29_bit(self):
        """build_j1939_id must produce a value ≤ 0x1FFFFFFF."""
        can_id = build_j1939_id(priority=7, pgn=0x3FFFF, source_address=0xFF)
        assert 0 <= can_id <= 0x1FFFFFFF

    def test_invalid_priority_raises(self):
        with pytest.raises(ValueError, match="Priority"):
            build_j1939_id(priority=8, pgn=PGN_EEC1, source_address=0x00)

    def test_invalid_source_address_raises(self):
        with pytest.raises(ValueError, match="Source address"):
            build_j1939_id(priority=6, pgn=PGN_EEC1, source_address=0x100)


# ---------------------------------------------------------------------------
# CANFrame
# ---------------------------------------------------------------------------

class TestCANFrame:
    """Tests for the CANFrame data class."""

    def test_create_minimal_frame(self):
        f = CANFrame(can_id=0x18FEF100, data=b"\x01\x02\x03\x04\x05\x06\x07\x08")
        assert f.dlc == 8
        assert f.hex_data() == "0102030405060708"

    def test_empty_payload(self):
        f = CANFrame(can_id=0x18FEF100, data=b"")
        assert f.dlc == 0

    def test_payload_too_long_raises(self):
        with pytest.raises(ValueError, match="8 bytes"):
            CANFrame(can_id=0x18FEF100, data=bytes(9))

    def test_invalid_extended_id_raises(self):
        with pytest.raises(ValueError, match="29-bit"):
            CANFrame(can_id=0x20000000, data=b"", is_extended=True)

    def test_invalid_standard_id_raises(self):
        with pytest.raises(ValueError, match="11-bit"):
            CANFrame(can_id=0x800, data=b"", is_extended=False)

    def test_data_must_be_bytes(self):
        with pytest.raises(TypeError, match="bytes"):
            CANFrame(can_id=0x18FEF100, data="not bytes")  # type: ignore[arg-type]

    def test_timestamp_stored(self):
        f = CANFrame(can_id=0x18FEF100, data=b"\xFF", timestamp=12345.678)
        assert f.timestamp == pytest.approx(12345.678)


# ---------------------------------------------------------------------------
# J1939Frame
# ---------------------------------------------------------------------------

class TestJ1939Frame:
    """Tests for J1939Frame creation and properties."""

    def test_from_can_frame_pdu2(self):
        """CCVS1 (PDU2) frame should have broadcast destination."""
        raw = CANFrame(can_id=0x18FEF100, data=bytes(8), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        assert frame.pgn == PGN_CCVS1
        assert frame.priority == 6
        assert frame.source_address == 0x00
        assert frame.is_broadcast
        assert frame.destination_address == ADDRESS_GLOBAL

    def test_from_can_frame_pdu1(self):
        """PDU1 frame should expose the destination address."""
        can_id = build_j1939_id(6, PGN_TP_CM, 0x01, 0x02)
        raw = CANFrame(can_id=can_id, data=bytes(8), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        assert not frame.is_broadcast
        assert frame.destination_address == 0x02
        assert frame.source_address == 0x01

    def test_from_standard_frame_raises(self):
        """J1939 requires extended (29-bit) frames."""
        raw = CANFrame(can_id=0x123, data=bytes(8), is_extended=False)
        with pytest.raises(ValueError, match="29-bit extended"):
            J1939Frame.from_can_frame(raw)

    def test_dlc_forwarded(self):
        raw = CANFrame(can_id=0x18FEF100, data=bytes(8), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        assert frame.dlc == 8

    def test_data_accessible(self):
        payload = bytes(range(8))
        raw = CANFrame(can_id=0x18FEF100, data=payload, is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        assert frame.data == payload
