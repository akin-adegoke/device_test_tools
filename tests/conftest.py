"""Shared pytest fixtures and sample data for J1939 test suite."""
from __future__ import annotations

import pytest

from j1939.constants import (
    PGN_EEC1,
    PGN_CCVS1,
    PGN_ET1,
    PGN_EFL_P1,
    PGN_VEP1,
    PGN_HOURS,
    PGN_ADDRESS_CLAIMED,
    PGN_TP_CM,
    PGN_TP_DT,
    TP_CM_BAM,
)
from j1939.frame import CANFrame, J1939Frame, build_j1939_id


# ---------------------------------------------------------------------------
# Raw CAN frame factories
# ---------------------------------------------------------------------------

@pytest.fixture
def make_can_frame():
    """Factory: create a CANFrame from a hex string."""
    def _factory(can_id: int, data_hex: str, timestamp: float = 0.0) -> CANFrame:
        return CANFrame(
            can_id=can_id,
            data=bytes.fromhex(data_hex),
            timestamp=timestamp,
            is_extended=True,
            interface="vcan0",
        )
    return _factory


@pytest.fixture
def make_j1939_frame(make_can_frame):
    """Factory: create a J1939Frame from priority, pgn, sa and data hex."""
    def _factory(
        priority: int,
        pgn: int,
        source_address: int,
        data_hex: str,
        destination_address: int = 0xFF,
        timestamp: float = 0.0,
    ) -> J1939Frame:
        can_id = build_j1939_id(priority, pgn, source_address, destination_address)
        frame = make_can_frame(can_id, data_hex, timestamp)
        return J1939Frame.from_can_frame(frame)
    return _factory


# ---------------------------------------------------------------------------
# Standard test frames
# ---------------------------------------------------------------------------

@pytest.fixture
def eec1_frame(make_j1939_frame) -> J1939Frame:
    """EEC1 frame: Engine Speed ≈ 800 rpm, Accel Pedal 0 %."""
    # SPN 190 (Engine Speed): bytes 3-4 little-endian
    # 800 rpm / 0.125 = raw 6400 = 0x1900
    # byte3=0x00, byte4=0x19
    # SPN 91 (Accel Pedal): byte1, 0/0.4 = 0
    # SPN 512 (Driver Demand %torque): byte2, raw 125 → 0 %
    return make_j1939_frame(
        priority=3,
        pgn=PGN_EEC1,
        source_address=0x00,
        data_hex="FF007D001900FF00",
    )


@pytest.fixture
def ccvs1_frame(make_j1939_frame) -> J1939Frame:
    """CCVS1 frame: Vehicle Speed ≈ 80 km/h."""
    # SPN 84 (Wheel Speed): bytes 1-2 LE, scale=1/256
    # 80 km/h * 256 = 20480 = 0x5000 → byte1=0x00, byte2=0x50
    return make_j1939_frame(
        priority=6,
        pgn=PGN_CCVS1,
        source_address=0x00,
        data_hex="0000500000000000",
    )


@pytest.fixture
def et1_frame(make_j1939_frame) -> J1939Frame:
    """ET1 frame: Coolant Temp = 80 °C."""
    # SPN 110 (Coolant Temp): byte0, raw = 80+40 = 120 = 0x78
    return make_j1939_frame(
        priority=6,
        pgn=PGN_ET1,
        source_address=0x00,
        data_hex="78FFFFFFFFFFFFFF",
    )


@pytest.fixture
def address_claimed_frame(make_can_frame) -> J1939Frame:
    """Address Claimed frame from SA=0x80."""
    # PGN_ADDRESS_CLAIMED = 0xEE00, PDU2 PF=0xEE, PS=0x00 (global)
    # CAN ID = (6 << 26) | (0xEE << 16) | (0x00 << 8) | 0x80
    can_id = build_j1939_id(6, PGN_ADDRESS_CLAIMED, 0x80)
    frame = make_can_frame(can_id, "0102030405060708")
    return J1939Frame.from_can_frame(frame)


@pytest.fixture
def bam_announce_frame(make_can_frame) -> J1939Frame:
    """TP.CM_BAM announcing a 20-byte message for PGN 0xFECA (DM1)."""
    # PGN_TP_CM = 0xEC00, PDU1 PF=0xEC, dest=0xFF (global)
    can_id = build_j1939_id(7, PGN_TP_CM, 0x01, 0xFF)
    # BAM: [0x20, size_lo, size_hi, num_packets, 0xFF, pgn_lo, pgn_mid, pgn_hi]
    # size=20, packets=3, pgn=0xFECA
    data = bytes([TP_CM_BAM, 20, 0, 3, 0xFF, 0xCA, 0xFE, 0x00])
    frame = CANFrame(can_id=can_id, data=data, timestamp=1.0, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(frame)
