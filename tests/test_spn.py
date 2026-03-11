"""Tests for SPN signal extraction and scaling."""
from __future__ import annotations

import pytest

from j1939.spn import (
    decode_spn,
    extract_bits,
    get_spn_definition,
    list_spns_for_pgn,
    is_in_operational_range,
    SPNValue,
)
from j1939.constants import (
    PGN_EEC1,
    PGN_CCVS1,
    PGN_ET1,
    PGN_EFL_P1,
    PGN_VEP1,
    PGN_HOURS,
    SPN_NOT_AVAILABLE_1BYTE,
    SPN_ERROR_INDICATOR_1BYTE,
    SPN_NOT_AVAILABLE_2BYTE,
    SPN_ERROR_INDICATOR_2BYTE,
)


# ---------------------------------------------------------------------------
# extract_bits
# ---------------------------------------------------------------------------

class TestExtractBits:
    """Unit tests for the low-level bit extraction function."""

    def test_extract_first_byte(self):
        data = bytes([0xAB, 0x00, 0x00])
        assert extract_bits(data, byte_offset=0, bit_offset=0, length_bits=8) == 0xAB

    def test_extract_second_byte(self):
        data = bytes([0x00, 0xCD, 0x00])
        assert extract_bits(data, byte_offset=1, bit_offset=0, length_bits=8) == 0xCD

    def test_extract_16_bit_little_endian(self):
        # 0x1900 in little-endian = [0x00, 0x19]
        data = bytes([0x00, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        result = extract_bits(data, byte_offset=0, bit_offset=0, length_bits=16)
        assert result == 0x1900

    def test_extract_sub_byte_bits(self):
        # Bits 6-7 of byte 0: byte=0b11000000 → bits 6-7 = 0b11 = 3
        data = bytes([0b11000000])
        result = extract_bits(data, byte_offset=0, bit_offset=6, length_bits=2)
        assert result == 3

    def test_extract_single_bit(self):
        data = bytes([0b00000100])  # bit 2 is set
        assert extract_bits(data, byte_offset=0, bit_offset=2, length_bits=1) == 1
        assert extract_bits(data, byte_offset=0, bit_offset=0, length_bits=1) == 0

    def test_extract_across_byte_boundary(self):
        # Extract 4 bits starting at bit 6 of byte 0 (crosses into byte 1)
        data = bytes([0b11000000, 0b00001010])
        # bits 6-7 of byte0 = 0b11, bits 0-1 of byte1 = 0b10
        # combined (LE): 0b1011 = 11
        result = extract_bits(data, byte_offset=0, bit_offset=6, length_bits=4)
        assert result == 0b1011

    def test_out_of_range_raises_index_error(self):
        data = bytes([0x00, 0x00])
        with pytest.raises(IndexError):
            extract_bits(data, byte_offset=0, bit_offset=0, length_bits=32)

    def test_32_bit_extraction(self):
        data = bytes([0x78, 0x56, 0x34, 0x12, 0x00, 0x00, 0x00, 0x00])
        result = extract_bits(data, byte_offset=0, bit_offset=0, length_bits=32)
        assert result == 0x12345678


# ---------------------------------------------------------------------------
# decode_spn – Engine Speed (SPN 190)
# ---------------------------------------------------------------------------

class TestDecodeSPNEngineSpeed:
    """Tests for Engine Speed (SPN 190) in EEC1 payload."""

    # EEC1 payload layout: byte0=status, byte1=accel, byte2=drv_demand,
    # byte3-4=engine_speed (LE 16-bit), bytes5-7=other
    def _make_eec1_payload(self, speed_raw: int) -> bytes:
        lo = speed_raw & 0xFF
        hi = (speed_raw >> 8) & 0xFF
        return bytes([0xFF, 0x00, 0x7D, lo, hi, 0xFF, 0xFF, 0xFF])

    def test_idle_speed_800_rpm(self):
        # 800 rpm / 0.125 = 6400 = 0x1900
        payload = self._make_eec1_payload(6400)
        sv = decode_spn(190, payload)
        assert sv.spn == 190
        assert sv.engineering_value == pytest.approx(800.0)
        assert sv.unit == "rpm"
        assert not sv.is_error
        assert not sv.is_not_available

    def test_zero_rpm(self):
        payload = self._make_eec1_payload(0)
        sv = decode_spn(190, payload)
        assert sv.engineering_value == pytest.approx(0.0)

    def test_max_speed_8031_875_rpm(self):
        # 8031.875 / 0.125 = 64255 = 0xFAFF
        payload = self._make_eec1_payload(0xFAFF)
        sv = decode_spn(190, payload)
        assert sv.engineering_value == pytest.approx(8031.875, rel=1e-4)

    def test_not_available_indicator(self):
        payload = self._make_eec1_payload(SPN_NOT_AVAILABLE_2BYTE)
        sv = decode_spn(190, payload)
        assert sv.is_not_available
        assert sv.engineering_value is None

    def test_error_indicator(self):
        payload = self._make_eec1_payload(SPN_ERROR_INDICATOR_2BYTE)
        sv = decode_spn(190, payload)
        assert sv.is_error
        assert sv.engineering_value is None

    def test_name_is_engine_speed(self):
        payload = self._make_eec1_payload(6400)
        sv = decode_spn(190, payload)
        assert sv.name == "Engine Speed"


# ---------------------------------------------------------------------------
# decode_spn – Accelerator Pedal (SPN 91)
# ---------------------------------------------------------------------------

class TestDecodeSPNAcceleratorPedal:

    def _make_eec1_payload(self, accel_raw: int) -> bytes:
        return bytes([0xFF, accel_raw, 0x7D, 0x00, 0x00, 0xFF, 0xFF, 0xFF])

    def test_zero_percent(self):
        sv = decode_spn(91, self._make_eec1_payload(0))
        assert sv.engineering_value == pytest.approx(0.0)
        assert sv.unit == "%"

    def test_50_percent(self):
        # 50 % / 0.4 = 125
        sv = decode_spn(91, self._make_eec1_payload(125))
        assert sv.engineering_value == pytest.approx(50.0)

    def test_full_throttle_100_percent(self):
        # 100 % / 0.4 = 250
        sv = decode_spn(91, self._make_eec1_payload(250))
        assert sv.engineering_value == pytest.approx(100.0)

    def test_not_available(self):
        sv = decode_spn(91, self._make_eec1_payload(SPN_NOT_AVAILABLE_1BYTE))
        assert sv.is_not_available

    def test_error_indicator(self):
        sv = decode_spn(91, self._make_eec1_payload(SPN_ERROR_INDICATOR_1BYTE))
        assert sv.is_error


# ---------------------------------------------------------------------------
# decode_spn – Vehicle Speed (SPN 84)
# ---------------------------------------------------------------------------

class TestDecodeSPNVehicleSpeed:

    def _make_ccvs1_payload(self, speed_raw: int) -> bytes:
        lo = speed_raw & 0xFF
        hi = (speed_raw >> 8) & 0xFF
        return bytes([0x00, lo, hi, 0x00, 0x00, 0x00, 0x00, 0x00])

    def test_zero_speed(self):
        sv = decode_spn(84, self._make_ccvs1_payload(0))
        assert sv.engineering_value == pytest.approx(0.0)
        assert sv.unit == "km/h"

    def test_80_km_h(self):
        # 80 * 256 = 20480 = 0x5000
        sv = decode_spn(84, self._make_ccvs1_payload(0x5000))
        assert sv.engineering_value == pytest.approx(80.0, rel=1e-4)

    def test_not_available(self):
        sv = decode_spn(84, self._make_ccvs1_payload(SPN_NOT_AVAILABLE_2BYTE))
        assert sv.is_not_available


# ---------------------------------------------------------------------------
# decode_spn – Coolant Temperature (SPN 110)
# ---------------------------------------------------------------------------

class TestDecodeSPNCoolantTemperature:

    def _make_et1_payload(self, temp_raw: int) -> bytes:
        return bytes([temp_raw, 0xFE, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF])

    def test_minus_40_degrees(self):
        # -40 °C: raw = 0 → 0 * 1.0 + (-40) = -40
        sv = decode_spn(110, self._make_et1_payload(0))
        assert sv.engineering_value == pytest.approx(-40.0)
        assert sv.unit == "°C"

    def test_20_degrees(self):
        # 20 °C: raw = 60 → 60 * 1 - 40 = 20
        sv = decode_spn(110, self._make_et1_payload(60))
        assert sv.engineering_value == pytest.approx(20.0)

    def test_80_degrees(self):
        # 80 °C: raw = 120 → 120 - 40 = 80
        sv = decode_spn(110, self._make_et1_payload(120))
        assert sv.engineering_value == pytest.approx(80.0)

    def test_210_degrees_max(self):
        sv = decode_spn(110, self._make_et1_payload(250))
        assert sv.engineering_value == pytest.approx(210.0)

    def test_not_available(self):
        sv = decode_spn(110, self._make_et1_payload(SPN_NOT_AVAILABLE_1BYTE))
        assert sv.is_not_available


# ---------------------------------------------------------------------------
# Unknown SPN raises KeyError
# ---------------------------------------------------------------------------

def test_unknown_spn_raises_key_error():
    with pytest.raises(KeyError):
        decode_spn(99999, bytes(8))


# ---------------------------------------------------------------------------
# list_spns_for_pgn
# ---------------------------------------------------------------------------

class TestListSPNsForPGN:

    def test_eec1_has_expected_spns(self):
        spns = list_spns_for_pgn(PGN_EEC1)
        assert 190 in spns  # Engine Speed
        assert 91 in spns   # Accelerator Pedal

    def test_ccvs1_has_vehicle_speed(self):
        spns = list_spns_for_pgn(PGN_CCVS1)
        assert 84 in spns

    def test_unknown_pgn_returns_empty_list(self):
        assert list_spns_for_pgn(0x9999) == []


# ---------------------------------------------------------------------------
# is_in_operational_range
# ---------------------------------------------------------------------------

class TestIsInOperationalRange:

    def test_valid_speed_in_range(self):
        sv = SPNValue(spn=190, name="Engine Speed", raw_value=6400,
                      engineering_value=800.0, unit="rpm")
        assert is_in_operational_range(sv)

    def test_negative_speed_out_of_range(self):
        sv = SPNValue(spn=190, name="Engine Speed", raw_value=0,
                      engineering_value=-1.0, unit="rpm")
        assert not is_in_operational_range(sv)

    def test_speed_above_max_out_of_range(self):
        sv = SPNValue(spn=190, name="Engine Speed", raw_value=0,
                      engineering_value=9000.0, unit="rpm")
        assert not is_in_operational_range(sv)

    def test_not_available_not_in_range(self):
        sv = SPNValue(spn=190, name="Engine Speed", raw_value=0xFFFF,
                      engineering_value=None, unit="rpm", is_not_available=True)
        assert not is_in_operational_range(sv)

    def test_error_not_in_range(self):
        sv = SPNValue(spn=190, name="Engine Speed", raw_value=0xFE00,
                      engineering_value=None, unit="rpm", is_error=True)
        assert not is_in_operational_range(sv)

    def test_unknown_spn_not_in_range(self):
        sv = SPNValue(spn=99999, name="Unknown", raw_value=0,
                      engineering_value=50.0, unit="unit")
        assert not is_in_operational_range(sv)


# ---------------------------------------------------------------------------
# get_spn_definition
# ---------------------------------------------------------------------------

class TestGetSPNDefinition:

    def test_known_spn_returns_dict(self):
        defn = get_spn_definition(190)
        assert defn is not None
        assert defn["name"] == "Engine Speed"
        assert defn["unit"] == "rpm"

    def test_unknown_spn_returns_none(self):
        assert get_spn_definition(99999) is None
