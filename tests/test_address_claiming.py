"""Tests for J1939 address claiming mechanism.

Address claiming is the network management process by which ECUs acquire
unique source addresses on the J1939 bus. The protocol is defined in
J1939-81 and uses the Address Claimed PGN (0xEE00).

Key rules:
- On power-up each ECU claims its address by transmitting a
  "Address Claimed" message containing its NAME (8 bytes).
- If two ECUs claim the same address the one with the lower NAME
  (treated as a 64-bit unsigned integer) wins.
- The loser must either choose a new address or stop transmitting.
- An ECU unable to claim any address sends "Cannot Claim Address"
  (source address = 0xFE = NULL address).
"""
from __future__ import annotations

import pytest

from j1939.frame import CANFrame, J1939Frame, build_j1939_id, parse_j1939_id, compute_pgn
from j1939.constants import (
    ADDRESS_GLOBAL,
    ADDRESS_NULL,
    PGN_ADDRESS_CLAIMED,
    PGN_COMMANDED_ADDRESS,
    PGN_REQUEST,
)
from j1939.validator import J1939Validator, Severity


# ---------------------------------------------------------------------------
# NAME helpers
# ---------------------------------------------------------------------------

def _encode_name(
    arbitrary_address_capable: int = 0,
    industry_group: int = 0,
    vehicle_system_instance: int = 0,
    vehicle_system: int = 0,
    function: int = 0,
    function_instance: int = 0,
    ecu_instance: int = 0,
    manufacturer_code: int = 0,
    identity_number: int = 0,
) -> bytes:
    """Encode a J1939 NAME field into 8 bytes (little-endian bit fields)."""
    # Bits 63: Arbitrary Address Capable (1 bit)
    # Bits 62-60: Industry Group (3 bits)
    # Bits 59-56: Vehicle System Instance (4 bits)
    # Bits 55-49: Vehicle System (7 bits)
    # Bit 48: Reserved (must be 0)
    # Bits 47-40: Function (8 bits)
    # Bits 39-35: Function Instance (5 bits)
    # Bits 34-32: ECU Instance (3 bits)
    # Bits 31-21: Manufacturer Code (11 bits)
    # Bits 20-0: Identity Number (21 bits)

    word_lo = identity_number & 0x1FFFFF
    word_lo |= (manufacturer_code & 0x7FF) << 21

    byte4 = ecu_instance & 0x07
    byte4 |= (function_instance & 0x1F) << 3
    byte5 = function & 0xFF
    byte6 = 0  # reserved bit, vehicle_system
    byte6 |= (vehicle_system & 0x7F) << 1
    byte7 = vehicle_system_instance & 0x0F
    byte7 |= (industry_group & 0x07) << 4
    byte7 |= (arbitrary_address_capable & 0x01) << 7

    name = (
        word_lo.to_bytes(4, "little")
        + bytes([byte4, byte5, byte6, byte7])
    )
    return name


def _make_address_claimed_frame(source: int, name: bytes,
                                dest: int = ADDRESS_GLOBAL) -> J1939Frame:
    """Build an Address Claimed J1939 frame."""
    assert len(name) == 8, "NAME must be exactly 8 bytes"
    can_id = build_j1939_id(6, PGN_ADDRESS_CLAIMED, source, dest)
    raw = CANFrame(can_id=can_id, data=name, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(raw)


def _make_request_frame(source: int, requested_pgn: int,
                        dest: int = ADDRESS_GLOBAL) -> J1939Frame:
    """Build a Request (PGN 59904) frame."""
    data = requested_pgn.to_bytes(3, "little")
    can_id = build_j1939_id(6, PGN_REQUEST, source, dest)
    raw = CANFrame(can_id=can_id, data=data, is_extended=True, interface="vcan0")
    return J1939Frame.from_can_frame(raw)


# ---------------------------------------------------------------------------
# Address Claimed frame structure
# ---------------------------------------------------------------------------

class TestAddressClaimedFrame:
    """Verify Address Claimed frame is correctly formed and parsed."""

    def test_pgn_is_address_claimed(self):
        name = _encode_name()
        frame = _make_address_claimed_frame(0x80, name)
        assert frame.pgn == PGN_ADDRESS_CLAIMED

    def test_source_address_preserved(self):
        name = _encode_name()
        frame = _make_address_claimed_frame(0x3C, name)
        assert frame.source_address == 0x3C

    def test_destination_is_global(self):
        name = _encode_name()
        frame = _make_address_claimed_frame(0x80, name)
        assert frame.destination_address == ADDRESS_GLOBAL

    def test_payload_is_8_bytes(self):
        name = _encode_name()
        frame = _make_address_claimed_frame(0x80, name)
        assert frame.dlc == 8

    def test_name_payload_matches(self):
        name = _encode_name(identity_number=42, manufacturer_code=100)
        frame = _make_address_claimed_frame(0x80, name)
        assert frame.data == name

    def test_cannot_claim_uses_null_source(self):
        """Cannot Claim Address uses source address 0xFE (NULL)."""
        name = _encode_name()
        frame = _make_address_claimed_frame(ADDRESS_NULL, name)
        assert frame.source_address == ADDRESS_NULL

    def test_priority_is_6(self):
        """Address Claimed messages use priority 6."""
        name = _encode_name()
        frame = _make_address_claimed_frame(0x80, name)
        assert frame.priority == 6


# ---------------------------------------------------------------------------
# NAME encoding and comparison
# ---------------------------------------------------------------------------

class TestNAMEEncoding:
    """Verify NAME encoding logic."""

    def test_name_is_8_bytes(self):
        name = _encode_name()
        assert len(name) == 8

    def test_identity_number_stored(self):
        name = _encode_name(identity_number=0x12345)
        value = int.from_bytes(name[:4], "little") & 0x1FFFFF
        assert value == 0x12345

    def test_manufacturer_code_stored(self):
        name = _encode_name(manufacturer_code=0x500)
        value = (int.from_bytes(name[:4], "little") >> 21) & 0x7FF
        assert value == 0x500

    def test_arbitrary_address_capable_set(self):
        name = _encode_name(arbitrary_address_capable=1)
        assert name[7] & 0x80  # bit 7 of byte 7

    def test_lower_name_wins_arbitration(self):
        """The ECU with the numerically lower 64-bit NAME value wins."""
        name_winner = _encode_name(identity_number=1)
        name_loser = _encode_name(identity_number=2)

        winner_int = int.from_bytes(name_winner, "little")
        loser_int = int.from_bytes(name_loser, "little")

        assert winner_int < loser_int

    def test_equal_names_no_winner(self):
        """Two ECUs with identical NAMEs cannot coexist."""
        name_a = _encode_name(identity_number=42)
        name_b = _encode_name(identity_number=42)
        assert int.from_bytes(name_a, "little") == int.from_bytes(name_b, "little")


# ---------------------------------------------------------------------------
# Request for Address Claimed
# ---------------------------------------------------------------------------

class TestRequestForAddressClaimed:

    def test_request_pgn_is_correct(self):
        frame = _make_request_frame(0x20, PGN_ADDRESS_CLAIMED)
        assert frame.pgn == PGN_REQUEST

    def test_request_payload_encodes_target_pgn(self):
        frame = _make_request_frame(0x20, PGN_ADDRESS_CLAIMED)
        requested = int.from_bytes(frame.data[:3], "little")
        assert requested == PGN_ADDRESS_CLAIMED

    def test_request_to_global(self):
        frame = _make_request_frame(0x20, PGN_ADDRESS_CLAIMED)
        assert frame.destination_address == ADDRESS_GLOBAL


# ---------------------------------------------------------------------------
# Validation of Address Claimed frames
# ---------------------------------------------------------------------------

class TestAddressClaimedValidation:
    """Run the J1939Validator against Address Claimed frames."""

    def test_valid_address_claimed_passes(self):
        name = _encode_name(identity_number=100, manufacturer_code=50)
        frame = _make_address_claimed_frame(0x80, name)
        result = J1939Validator().validate(frame)
        # No ERROR-level issues expected
        assert result.is_valid

    def test_cannot_claim_produces_v003_warning(self):
        """Cannot Claim (SA=0xFE) triggers V003 warning."""
        name = _encode_name()
        frame = _make_address_claimed_frame(ADDRESS_NULL, name)
        result = J1939Validator().validate(frame)
        codes = [i.code for i in result.issues]
        assert "V003" in codes
        v003 = next(i for i in result.issues if i.code == "V003")
        assert v003.severity == Severity.WARNING
        # But it is still "valid" from a structural perspective (no ERROR)
        assert result.is_valid

    def test_wrong_dlc_produces_v004_error(self):
        """Address Claimed must be exactly 8 bytes."""
        can_id = build_j1939_id(6, PGN_ADDRESS_CLAIMED, 0x80)
        raw = CANFrame(can_id=can_id, data=bytes(5), is_extended=True)
        frame = J1939Frame.from_can_frame(raw)
        result = J1939Validator().validate(frame)
        codes = [i.code for i in result.issues]
        assert "V004" in codes
        assert not result.is_valid
