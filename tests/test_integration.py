"""Tests for end-to-end integration scenarios combining multiple J1939 components."""
from __future__ import annotations

import pytest

from j1939.frame import CANFrame, J1939Frame, build_j1939_id
from j1939.decoder import J1939Decoder
from j1939.validator import J1939Validator, Severity
from j1939.transport import TransportProtocolHandler
from j1939.candump import parse_line
from j1939.constants import (
    ADDRESS_GLOBAL,
    PGN_EEC1,
    PGN_CCVS1,
    PGN_ET1,
    PGN_EFL_P1,
    PGN_TP_CM,
    PGN_TP_DT,
    PGN_DM1,
    TP_CM_BAM,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _j1939_from_candump(line: str) -> J1939Frame:
    raw = parse_line(line)
    return J1939Frame.from_can_frame(raw)


# ---------------------------------------------------------------------------
# Decode + Validate roundtrip
# ---------------------------------------------------------------------------

class TestDecodeValidateRoundtrip:
    """Integration: decode a frame then validate it."""

    def test_valid_eec1_decode_and_validate(self):
        line = "(1609459200.000000) vcan0 18F00400#FF007D001900FF00"
        frame = _j1939_from_candump(line)

        msg = J1939Decoder().decode(frame)
        result = J1939Validator().validate(frame)

        assert msg.is_known_pgn
        speed = msg.get_spn(190)
        assert speed is not None
        assert speed.engineering_value == pytest.approx(800.0)
        assert result.is_valid

    def test_valid_ccvs1_decode_and_validate(self):
        line = "(1609459200.001000) vcan0 18FEF100#0000500000000000"
        frame = _j1939_from_candump(line)

        msg = J1939Decoder().decode(frame)
        result = J1939Validator().validate(frame)

        speed = msg.get_spn(84)
        assert speed is not None
        assert speed.engineering_value == pytest.approx(80.0, rel=1e-4)
        assert result.is_valid

    def test_message_with_wrong_dlc_fails_validation(self):
        can_id = build_j1939_id(6, PGN_EEC1, 0x00)
        raw = CANFrame(can_id=can_id, data=bytes(4), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)

        result = J1939Validator().validate(frame)
        assert not result.is_valid
        codes = [i.code for i in result.errors()]
        assert "V004" in codes


# ---------------------------------------------------------------------------
# Multi-message sequence analysis
# ---------------------------------------------------------------------------

class TestMessageSequenceAnalysis:
    """Analyse a sequence of messages from a simulated candump session."""

    CANDUMP_SEQUENCE = [
        "(1000.000000) vcan0 18F00400#FF007D001900FF00",  # EEC1 – 800 rpm
        "(1000.010000) vcan0 18FEF100#0000500000000000",  # CCVS1 – 80 km/h
        "(1000.020000) vcan0 18FEEE00#78FEFFFFFF00FFFF",  # ET1 – 80°C coolant
        "(1000.030000) vcan0 18F00400#FF007D40A400FF00",  # EEC1 – different speed
    ]

    def test_sequence_all_valid(self):
        validator = J1939Validator()
        for line in self.CANDUMP_SEQUENCE:
            frame = _j1939_from_candump(line)
            result = validator.validate(frame)
            assert result.is_valid, f"Frame failed: {line}, issues: {result.issues}"

    def test_sequence_pgns_match_expected(self):
        expected_pgns = [PGN_EEC1, PGN_CCVS1, PGN_ET1, PGN_EEC1]
        for line, expected_pgn in zip(self.CANDUMP_SEQUENCE, expected_pgns):
            frame = _j1939_from_candump(line)
            assert frame.pgn == expected_pgn

    def test_eec1_speeds_in_sequence(self):
        decoder = J1939Decoder()
        eec1_frames = [
            _j1939_from_candump(line)
            for line in self.CANDUMP_SEQUENCE
            if "18F004" in line
        ]
        assert len(eec1_frames) == 2

        speeds = []
        for frame in eec1_frames:
            msg = decoder.decode(frame)
            speed = msg.get_spn(190)
            if speed and not speed.is_not_available and not speed.is_error:
                speeds.append(speed.engineering_value)

        assert len(speeds) == 2
        assert all(0 <= s <= 8031.875 for s in speeds)


# ---------------------------------------------------------------------------
# BAM TP + Validation integration
# ---------------------------------------------------------------------------

class TestTPAndValidationIntegration:
    """Verify TP reassembly produces data that can be validated."""

    def test_bam_reassembly_result_has_correct_pgn(self):
        handler = TransportProtocolHandler()

        can_id_cm = build_j1939_id(7, PGN_TP_CM, 0x01, ADDRESS_GLOBAL)
        pgn_bytes = PGN_DM1.to_bytes(3, "little")
        cm_data = bytes([TP_CM_BAM, 14, 0, 2, 0xFF]) + pgn_bytes
        raw_cm = CANFrame(can_id=can_id_cm, data=cm_data, is_extended=True)
        cm_frame = J1939Frame.from_can_frame(raw_cm)

        can_id_dt = build_j1939_id(7, PGN_TP_DT, 0x01, ADDRESS_GLOBAL)
        dt1_data = bytes([0x01, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07])
        dt2_data = bytes([0x02, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0xFF])

        raw_dt1 = CANFrame(can_id=can_id_dt, data=dt1_data, is_extended=True)
        raw_dt2 = CANFrame(can_id=can_id_dt, data=dt2_data, is_extended=True)

        dt1_frame = J1939Frame.from_can_frame(raw_dt1)
        dt2_frame = J1939Frame.from_can_frame(raw_dt2)

        handler.process(cm_frame)
        handler.process(dt1_frame)
        result = handler.process(dt2_frame)

        assert result is not None
        assert result.pgn == PGN_DM1
        assert len(result.data) == 14


# ---------------------------------------------------------------------------
# Source address uniqueness tracking
# ---------------------------------------------------------------------------

class TestSourceAddressTracking:
    """Simulate tracking which source addresses are seen on the bus."""

    MULTI_SA_SEQUENCE = [
        "(1000.000000) vcan0 18F00400#FF007D001900FF00",  # SA=0x00
        "(1000.001000) vcan0 18FEF103#0000500000000000",  # SA=0x03
        "(1000.002000) vcan0 18FEEE00#78FEFFFFFF00FFFF",  # SA=0x00
        "(1000.003000) vcan0 18F00418#FF007D001900FF00",  # SA=0x18
    ]

    def test_unique_source_addresses_detected(self):
        seen_addresses = set()
        for line in self.MULTI_SA_SEQUENCE:
            frame = _j1939_from_candump(line)
            seen_addresses.add(frame.source_address)

        assert 0x00 in seen_addresses
        assert 0x03 in seen_addresses
        assert 0x18 in seen_addresses
        assert len(seen_addresses) == 3

    def test_pgn_per_source_address(self):
        from collections import defaultdict
        pgns_by_sa: dict = defaultdict(set)
        for line in self.MULTI_SA_SEQUENCE:
            frame = _j1939_from_candump(line)
            pgns_by_sa[frame.source_address].add(frame.pgn)

        assert PGN_EEC1 in pgns_by_sa[0x00]
        assert PGN_CCVS1 in pgns_by_sa[0x03]
        assert PGN_EEC1 in pgns_by_sa[0x18]
