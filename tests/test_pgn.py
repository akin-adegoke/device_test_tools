"""Tests for PGN utilities."""
from __future__ import annotations

import pytest

from j1939.pgn import get_pgn_info, is_pdu1, is_pdu2, is_valid_pgn, pgn_to_description
from j1939.constants import (
    PGN_EEC1,
    PGN_EEC2,
    PGN_CCVS1,
    PGN_ET1,
    PGN_EFL_P1,
    PGN_VEP1,
    PGN_HOURS,
    PGN_VD,
    PGN_ADDRESS_CLAIMED,
    PGN_REQUEST,
    PGN_TP_CM,
    PGN_TP_DT,
    PGN_DM1,
    PGN_DM2,
)


# ---------------------------------------------------------------------------
# get_pgn_info
# ---------------------------------------------------------------------------

class TestGetPGNInfo:
    """Tests for the PGN info lookup."""

    @pytest.mark.parametrize("pgn, expected_name", [
        (PGN_EEC1, "Electronic Engine Controller 1"),
        (PGN_EEC2, "Electronic Engine Controller 2"),
        (PGN_CCVS1, "Cruise Control / Vehicle Speed 1"),
        (PGN_ET1, "Engine Temperature 1"),
        (PGN_EFL_P1, "Engine Fluid Level / Pressure 1"),
        (PGN_VEP1, "Vehicle Electrical Power 1"),
        (PGN_HOURS, "Engine Hours, Revolutions"),
        (PGN_VD, "Vehicle Distance"),
        (PGN_ADDRESS_CLAIMED, "Address Claimed"),
        (PGN_REQUEST, "Request"),
        (PGN_TP_CM, "TP Connection Management"),
        (PGN_TP_DT, "TP Data Transfer"),
        (PGN_DM1, "Active Diagnostic Trouble Codes"),
        (PGN_DM2, "Previously Active DTCs"),
    ])
    def test_known_pgn_returns_info(self, pgn, expected_name):
        info = get_pgn_info(pgn)
        assert info is not None
        assert info.pgn == pgn
        assert info.name == expected_name

    def test_unknown_pgn_returns_none(self):
        info = get_pgn_info(0x9999)
        assert info is None

    def test_eec1_expected_length(self):
        info = get_pgn_info(PGN_EEC1)
        assert info.expected_length == 8

    def test_dm1_variable_length(self):
        """DM1 has variable length (indicated as -1)."""
        info = get_pgn_info(PGN_DM1)
        assert info.expected_length == -1

    def test_request_expected_length(self):
        info = get_pgn_info(PGN_REQUEST)
        assert info.expected_length == 3


# ---------------------------------------------------------------------------
# is_pdu1 / is_pdu2
# ---------------------------------------------------------------------------

class TestPDUFormat:
    """Tests for PDU format detection."""

    @pytest.mark.parametrize("pgn", [
        PGN_REQUEST,       # PF=0xEA < 0xF0
        PGN_ADDRESS_CLAIMED,  # PF=0xEE < 0xF0
        PGN_TP_CM,         # PF=0xEC < 0xF0
        PGN_TP_DT,         # PF=0xEB < 0xF0
    ])
    def test_pdu1_pgns(self, pgn):
        assert is_pdu1(pgn) is True
        assert is_pdu2(pgn) is False

    @pytest.mark.parametrize("pgn", [
        PGN_EEC1,    # PF=0xF0 >= 0xF0
        PGN_CCVS1,   # PF=0xFE >= 0xF0
        PGN_ET1,     # PF=0xFE >= 0xF0
        PGN_DM1,     # PF=0xFE >= 0xF0
    ])
    def test_pdu2_pgns(self, pgn):
        assert is_pdu2(pgn) is True
        assert is_pdu1(pgn) is False

    def test_boundary_pf_239_is_pdu1(self):
        pgn = 0xEF00  # PF=0xEF (239)
        assert is_pdu1(pgn)
        assert not is_pdu2(pgn)

    def test_boundary_pf_240_is_pdu2(self):
        pgn = 0xF004  # PF=0xF0 (240) → PDU2
        assert is_pdu2(pgn)
        assert not is_pdu1(pgn)


# ---------------------------------------------------------------------------
# is_valid_pgn
# ---------------------------------------------------------------------------

class TestIsValidPGN:
    """Tests for PGN range validation."""

    def test_zero_is_valid(self):
        assert is_valid_pgn(0)

    def test_max_18_bit_value_is_valid(self):
        assert is_valid_pgn(0x3FFFF)

    def test_value_above_18_bits_is_invalid(self):
        assert not is_valid_pgn(0x40000)

    def test_negative_is_invalid(self):
        assert not is_valid_pgn(-1)

    @pytest.mark.parametrize("pgn", [
        PGN_EEC1,
        PGN_CCVS1,
        PGN_DM1,
        PGN_ADDRESS_CLAIMED,
    ])
    def test_known_pgns_are_valid(self, pgn):
        assert is_valid_pgn(pgn)


# ---------------------------------------------------------------------------
# pgn_to_description
# ---------------------------------------------------------------------------

class TestPGNToDescription:
    """Tests for the human-readable PGN description helper."""

    def test_known_pgn_includes_name(self):
        desc = pgn_to_description(PGN_EEC1)
        assert "Electronic Engine Controller 1" in desc
        assert "0xF004" in desc

    def test_unknown_pgn_includes_hex(self):
        desc = pgn_to_description(0x1234)
        assert "0x1234" in desc
        assert "Unknown" in desc

    def test_zero_pgn_shows_correctly(self):
        desc = pgn_to_description(0)
        assert "0x0000" in desc
