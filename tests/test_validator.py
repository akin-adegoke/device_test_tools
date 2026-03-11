"""Tests for the J1939Validator."""
from __future__ import annotations

import pytest

from j1939.frame import CANFrame, J1939Frame, build_j1939_id
from j1939.validator import J1939Validator, Severity, ValidationIssue
from j1939.constants import (
    ADDRESS_GLOBAL,
    ADDRESS_NULL,
    PGN_EEC1,
    PGN_CCVS1,
    PGN_ET1,
    PGN_DM1,
    SPN_NOT_AVAILABLE_1BYTE,
    SPN_ERROR_INDICATOR_1BYTE,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_frame(pgn: int, data_hex: str, source: int = 0x00,
                priority: int = 6, dest: int = ADDRESS_GLOBAL) -> J1939Frame:
    can_id = build_j1939_id(priority, pgn, source, dest)
    raw = CANFrame(can_id=can_id, data=bytes.fromhex(data_hex), is_extended=True)
    return J1939Frame.from_can_frame(raw)


def _get_issue_codes(result) -> list[str]:
    return [i.code for i in result.issues]


# ---------------------------------------------------------------------------
# V001 – Priority
# ---------------------------------------------------------------------------

class TestPriorityValidation:

    def test_valid_priority_no_v001(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00", priority=3)
        result = J1939Validator().validate(frame)
        assert "V001" not in _get_issue_codes(result)

    def test_priority_0_is_valid(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00", priority=0)
        result = J1939Validator().validate(frame)
        assert "V001" not in _get_issue_codes(result)

    def test_priority_7_is_valid(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00", priority=7)
        result = J1939Validator().validate(frame)
        assert "V001" not in _get_issue_codes(result)

    def test_invalid_priority_raises_v001(self):
        """Manually construct a frame with an out-of-range priority."""
        # Direct construction bypassing build_j1939_id validation
        raw = CANFrame(can_id=0x18F00400, data=bytes(8), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        # Override priority via a fresh object with monkey-patched value
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=8,  # invalid
            pgn=PGN_EEC1,
            source_address=0x00,
        )
        result = J1939Validator().validate(frame_obj)
        assert "V001" in _get_issue_codes(result)
        v001 = next(i for i in result.issues if i.code == "V001")
        assert v001.severity == Severity.ERROR


# ---------------------------------------------------------------------------
# V002 – PGN validity
# ---------------------------------------------------------------------------

class TestPGNValidity:

    def test_known_pgn_no_v002(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00")
        result = J1939Validator().validate(frame)
        assert "V002" not in _get_issue_codes(result)

    def test_invalid_pgn_raises_v002(self):
        raw = CANFrame(can_id=0x18F00400, data=bytes(8), is_extended=True)
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=6,
            pgn=0x40000,  # > 0x3FFFF → invalid
            source_address=0x00,
        )
        result = J1939Validator().validate(frame_obj)
        assert "V002" in _get_issue_codes(result)

    def test_max_valid_pgn_no_v002(self):
        raw = CANFrame(can_id=0x18F00400, data=bytes(8), is_extended=True)
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=6,
            pgn=0x3FFFF,
            source_address=0x00,
        )
        result = J1939Validator().validate(frame_obj)
        assert "V002" not in _get_issue_codes(result)


# ---------------------------------------------------------------------------
# V003 – Source address
# ---------------------------------------------------------------------------

class TestSourceAddressValidation:

    def test_normal_source_address_no_v003(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00", source=0x00)
        result = J1939Validator().validate(frame)
        assert "V003" not in _get_issue_codes(result)

    def test_null_source_address_warning(self):
        """SA=0xFE (null) should produce a V003 WARNING."""
        raw = CANFrame(can_id=0x18F00400, data=bytes(8), is_extended=True)
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=6,
            pgn=PGN_EEC1,
            source_address=ADDRESS_NULL,
        )
        result = J1939Validator().validate(frame_obj)
        assert "V003" in _get_issue_codes(result)
        v003 = next(i for i in result.issues if i.code == "V003")
        assert v003.severity == Severity.WARNING


# ---------------------------------------------------------------------------
# V004 – DLC
# ---------------------------------------------------------------------------

class TestDLCValidation:

    def test_correct_dlc_no_v004(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00")
        result = J1939Validator().validate(frame)
        assert "V004" not in _get_issue_codes(result)

    def test_wrong_dlc_raises_v004(self):
        can_id = build_j1939_id(6, PGN_EEC1, 0x00)
        raw = CANFrame(can_id=can_id, data=bytes(4), is_extended=True)  # DLC=4, expected=8
        frame = J1939Frame.from_can_frame(raw)
        result = J1939Validator().validate(frame)
        assert "V004" in _get_issue_codes(result)
        v004 = next(i for i in result.issues if i.code == "V004")
        assert v004.severity == Severity.ERROR

    def test_variable_length_pgn_skips_dlc_check(self):
        """DM1 has variable length → V004 should not be raised."""
        can_id = build_j1939_id(6, PGN_DM1, 0x00)
        raw = CANFrame(can_id=can_id, data=bytes(4), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        result = J1939Validator().validate(frame)
        assert "V004" not in _get_issue_codes(result)


# ---------------------------------------------------------------------------
# V005 – SPN range
# ---------------------------------------------------------------------------

class TestSPNRangeValidation:

    def test_valid_engine_speed_no_v005(self):
        # 800 rpm → valid
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00")
        result = J1939Validator().validate(frame)
        v005_issues = [i for i in result.issues if i.code == "V005"]
        # Only informational N/A issues are allowed (from 0xFF fields)
        errors_warnings = [i for i in v005_issues
                           if i.severity in (Severity.ERROR, Severity.WARNING)]
        assert not errors_warnings

    def test_not_available_spn_produces_info_v005(self):
        # Coolant temp byte0 = 0xFF → not available
        frame = _make_frame(PGN_ET1, "FFFFFFFFFFFFFFFF")
        result = J1939Validator().validate(frame)
        codes = _get_issue_codes(result)
        assert "V005" in codes
        v005 = [i for i in result.issues if i.code == "V005"]
        # Not-available should be INFO, not ERROR
        assert all(i.severity == Severity.INFO for i in v005)

    def test_error_indicator_spn_produces_warning_v005(self):
        # Coolant temp byte0 = 0xFE → error indicator
        frame = _make_frame(PGN_ET1, "FEFFFFFFFEFFFFFF")
        result = J1939Validator().validate(frame)
        v005_warnings = [i for i in result.issues
                         if i.code == "V005" and i.severity == Severity.WARNING]
        assert len(v005_warnings) > 0


# ---------------------------------------------------------------------------
# V006 – Address loopback
# ---------------------------------------------------------------------------

class TestAddressLoopback:

    def test_different_src_dst_no_v006(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00",
                            source=0x01, dest=0x02)
        result = J1939Validator().validate(frame)
        assert "V006" not in _get_issue_codes(result)

    def test_broadcast_dst_no_v006(self):
        """Global destination should never trigger loopback check."""
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00", source=0xFF, dest=ADDRESS_GLOBAL)
        result = J1939Validator().validate(frame)
        assert "V006" not in _get_issue_codes(result)

    def test_same_src_and_dst_raises_v006(self):
        raw = CANFrame(can_id=0x18F00401, data=bytes(8), is_extended=True)
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=6,
            pgn=PGN_EEC1,
            source_address=0x01,
            destination_address=0x01,  # same as source → loopback
        )
        result = J1939Validator().validate(frame_obj)
        assert "V006" in _get_issue_codes(result)
        v006 = next(i for i in result.issues if i.code == "V006")
        assert v006.severity == Severity.ERROR


# ---------------------------------------------------------------------------
# V007 – Unknown PGN (INFO)
# ---------------------------------------------------------------------------

class TestUnknownPGN:

    def test_known_pgn_no_v007(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00")
        result = J1939Validator().validate(frame)
        assert "V007" not in _get_issue_codes(result)

    def test_unknown_pgn_raises_v007_info(self):
        raw = CANFrame(can_id=0x18F00400, data=bytes(8), is_extended=True)
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=6,
            pgn=0x1234,  # unknown PGN
            source_address=0x00,
        )
        result = J1939Validator().validate(frame_obj)
        assert "V007" in _get_issue_codes(result)
        v007 = next(i for i in result.issues if i.code == "V007")
        assert v007.severity == Severity.INFO


# ---------------------------------------------------------------------------
# Aggregate is_valid / has_warnings
# ---------------------------------------------------------------------------

class TestValidationResultHelpers:

    def test_valid_eec1_message_is_valid(self):
        frame = _make_frame(PGN_EEC1, "FF007D001900FF00")
        result = J1939Validator().validate(frame)
        assert result.is_valid

    def test_wrong_dlc_is_not_valid(self):
        can_id = build_j1939_id(6, PGN_EEC1, 0x00)
        raw = CANFrame(can_id=can_id, data=bytes(4), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        result = J1939Validator().validate(frame)
        assert not result.is_valid

    def test_errors_list_contains_only_errors(self):
        can_id = build_j1939_id(6, PGN_EEC1, 0x00)
        raw = CANFrame(can_id=can_id, data=bytes(4), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        result = J1939Validator().validate(frame)
        for issue in result.errors():
            assert issue.severity == Severity.ERROR

    def test_warnings_list_contains_only_warnings(self):
        raw = CANFrame(can_id=0x18F00400, data=bytes(8), is_extended=True)
        frame_obj = J1939Frame(
            can_frame=raw,
            priority=6,
            pgn=PGN_EEC1,
            source_address=ADDRESS_NULL,
        )
        result = J1939Validator().validate(frame_obj)
        for issue in result.warnings():
            assert issue.severity == Severity.WARNING
