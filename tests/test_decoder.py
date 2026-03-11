"""Tests for the J1939Decoder."""
from __future__ import annotations

import pytest

from j1939.decoder import J1939Decoder, DecodedMessage
from j1939.frame import CANFrame, J1939Frame, build_j1939_id
from j1939.constants import (
    PGN_EEC1,
    PGN_CCVS1,
    PGN_ET1,
    PGN_EFL_P1,
    PGN_VEP1,
    PGN_HOURS,
    PGN_DM1,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_j1939_frame(pgn: int, data_hex: str, source: int = 0x00,
                      priority: int = 6) -> J1939Frame:
    can_id = build_j1939_id(priority, pgn, source)
    raw = CANFrame(can_id=can_id, data=bytes.fromhex(data_hex), is_extended=True)
    return J1939Frame.from_can_frame(raw)


# ---------------------------------------------------------------------------
# EEC1 – Electronic Engine Controller 1
# ---------------------------------------------------------------------------

class TestDecodeEEC1:
    """Decode Engine Speed and Accelerator Pedal from EEC1 messages."""

    def test_decode_engine_speed_800_rpm(self):
        # byte3-4 LE: 800/0.125 = 6400 = 0x1900 → [0x00, 0x19]
        frame = _make_j1939_frame(PGN_EEC1, "FF007D001900FF00")
        msg = J1939Decoder().decode(frame)

        assert msg.is_known_pgn
        assert msg.pgn_info.name == "Electronic Engine Controller 1"

        speed = msg.get_spn(190)
        assert speed is not None
        assert speed.engineering_value == pytest.approx(800.0)

    def test_decode_accel_pedal_50_percent(self):
        # SPN 91 at byte1: 50%/0.4=125=0x7D
        frame = _make_j1939_frame(PGN_EEC1, "FF7D7D001900FF00")
        msg = J1939Decoder().decode(frame)

        accel = msg.get_spn(91)
        assert accel is not None
        assert accel.engineering_value == pytest.approx(50.0)

    def test_decode_returns_multiple_spns(self):
        frame = _make_j1939_frame(PGN_EEC1, "FF007D001900FF00")
        msg = J1939Decoder().decode(frame)
        assert len(msg.spn_values) >= 2  # at minimum SPN 190 and SPN 91

    def test_source_address_preserved(self):
        frame = _make_j1939_frame(PGN_EEC1, "FF007D001900FF00", source=0x3C)
        msg = J1939Decoder().decode(frame)
        assert msg.source_address == 0x3C


# ---------------------------------------------------------------------------
# CCVS1 – Vehicle Speed
# ---------------------------------------------------------------------------

class TestDecodeCCVS1:

    def test_decode_vehicle_speed_80_km_h(self):
        # SPN 84 bytes1-2: 80*256=20480=0x5000 → [0x00, 0x50]
        frame = _make_j1939_frame(PGN_CCVS1, "0000500000000000")
        msg = J1939Decoder().decode(frame)

        speed = msg.get_spn(84)
        assert speed is not None
        assert speed.engineering_value == pytest.approx(80.0, rel=1e-4)
        assert speed.unit == "km/h"

    def test_decode_vehicle_stopped(self):
        frame = _make_j1939_frame(PGN_CCVS1, "0000000000000000")
        msg = J1939Decoder().decode(frame)
        speed = msg.get_spn(84)
        assert speed.engineering_value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# ET1 – Engine Temperature
# ---------------------------------------------------------------------------

class TestDecodeET1:

    def test_decode_coolant_temp_80_celsius(self):
        # SPN 110 at byte0: 80°C → raw=80+40=120=0x78
        frame = _make_j1939_frame(PGN_ET1, "78FEFFFFFF00FFFF")
        msg = J1939Decoder().decode(frame)

        temp = msg.get_spn(110)
        assert temp is not None
        assert temp.engineering_value == pytest.approx(80.0)
        assert temp.unit == "°C"


# ---------------------------------------------------------------------------
# Unknown PGN
# ---------------------------------------------------------------------------

class TestDecodeUnknownPGN:

    def test_unknown_pgn_returns_no_spn_values(self):
        frame = _make_j1939_frame(0x1234, "0102030405060708")
        msg = J1939Decoder().decode(frame)

        assert not msg.is_known_pgn
        assert msg.pgn_info is None
        assert msg.spn_values == []

    def test_unknown_pgn_has_no_decode_errors(self):
        frame = _make_j1939_frame(0x1234, "0102030405060708")
        msg = J1939Decoder().decode(frame)
        assert msg.decode_errors == []


# ---------------------------------------------------------------------------
# get_spn helper
# ---------------------------------------------------------------------------

class TestGetSPN:

    def test_get_spn_returns_correct_value(self):
        frame = _make_j1939_frame(PGN_EEC1, "FF007D001900FF00")
        msg = J1939Decoder().decode(frame)
        sv = msg.get_spn(190)
        assert sv is not None
        assert sv.spn == 190

    def test_get_spn_returns_none_for_absent_spn(self):
        frame = _make_j1939_frame(PGN_EEC1, "FF007D001900FF00")
        msg = J1939Decoder().decode(frame)
        assert msg.get_spn(99999) is None
