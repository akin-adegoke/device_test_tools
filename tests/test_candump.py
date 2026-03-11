"""Tests for the candump log file parser."""
from __future__ import annotations

import os
import tempfile

import pytest

from j1939.candump import parse_line, parse_file, parse_j1939_file, iter_j1939_frames
from j1939.frame import CANFrame, J1939Frame
from j1939.constants import PGN_CCVS1, PGN_EEC1


# ---------------------------------------------------------------------------
# Sample log lines
# ---------------------------------------------------------------------------

VALID_EXTENDED_LINE = "(1609459200.000000) vcan0 18FEF100#0000500000000000"
VALID_STANDARD_LINE = "(1609459200.000001) can0 7FF#DEADBEEF"
COMMENT_LINE = "# This is a comment"
BLANK_LINE = "   "
WHITESPACE_LINE = "\n"


# ---------------------------------------------------------------------------
# parse_line
# ---------------------------------------------------------------------------

class TestParseLine:

    def test_parse_extended_frame(self):
        frame = parse_line(VALID_EXTENDED_LINE)
        assert frame is not None
        assert frame.is_extended
        assert frame.can_id == 0x18FEF100
        assert frame.data == bytes.fromhex("0000500000000000")
        assert frame.timestamp == pytest.approx(1609459200.0)
        assert frame.interface == "vcan0"

    def test_parse_standard_frame(self):
        frame = parse_line(VALID_STANDARD_LINE)
        assert frame is not None
        assert not frame.is_extended
        assert frame.can_id == 0x7FF
        assert frame.data == bytes.fromhex("DEADBEEF")

    def test_comment_line_returns_none(self):
        assert parse_line(COMMENT_LINE) is None

    def test_blank_line_returns_none(self):
        assert parse_line(BLANK_LINE) is None

    def test_whitespace_only_returns_none(self):
        assert parse_line(WHITESPACE_LINE) is None

    def test_dlc_8_payload(self):
        line = "(1000.000000) can0 18FEF100#0102030405060708"
        frame = parse_line(line)
        assert frame.dlc == 8

    def test_empty_payload(self):
        line = "(1000.000000) can0 18FEF100#"
        frame = parse_line(line)
        assert frame is not None
        assert frame.dlc == 0

    def test_different_interfaces(self):
        for iface in ("can0", "can1", "vcan0", "slcan0"):
            line = f"(1000.000000) {iface} 18FEF100#FF"
            frame = parse_line(line)
            assert frame.interface == iface

    def test_invalid_line_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_line("this is not a valid candump line")

    def test_eec1_line(self):
        line = "(1609459200.500000) vcan0 18F00400#FF007D001900FF00"
        frame = parse_line(line)
        assert frame.can_id == 0x18F00400
        assert frame.data == bytes.fromhex("FF007D001900FF00")

    def test_high_precision_timestamp(self):
        line = "(1609459200.123456) vcan0 18FEF100#FF"
        frame = parse_line(line)
        assert frame.timestamp == pytest.approx(1609459200.123456, rel=1e-9)


# ---------------------------------------------------------------------------
# parse_file and parse_j1939_file
# ---------------------------------------------------------------------------

SAMPLE_LOG_CONTENT = """\
# Sample candump log
(1609459200.000000) vcan0 18FEF100#0000500000000000
(1609459200.001000) vcan0 18F00400#FF007D001900FF00
(1609459200.002000) can0 7FF#AABBCCDD
(1609459200.003000) vcan0 18FEEE00#78FEFFFFFF00FFFF
"""


@pytest.fixture
def sample_log_file(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text(SAMPLE_LOG_CONTENT, encoding="utf-8")
    return log_file


class TestParseFile:

    def test_parse_file_returns_all_frames(self, sample_log_file):
        frames = parse_file(sample_log_file)
        assert len(frames) == 4  # 4 non-comment, non-blank lines

    def test_frame_order_preserved(self, sample_log_file):
        frames = parse_file(sample_log_file)
        timestamps = [f.timestamp for f in frames]
        assert timestamps == sorted(timestamps)

    def test_mixed_extended_and_standard(self, sample_log_file):
        frames = parse_file(sample_log_file)
        extended = [f for f in frames if f.is_extended]
        standard = [f for f in frames if not f.is_extended]
        assert len(extended) == 3
        assert len(standard) == 1

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_file(tmp_path / "nonexistent.log")

    def test_invalid_line_raises_value_error(self, tmp_path):
        bad_log = tmp_path / "bad.log"
        bad_log.write_text("(100.000000) vcan0 BAD_LINE\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Line 1"):
            parse_file(bad_log)


class TestParseJ1939File:

    def test_filters_standard_frames(self, sample_log_file):
        j1939_frames = parse_j1939_file(sample_log_file)
        # 3 extended frames in sample
        assert len(j1939_frames) == 3

    def test_returns_j1939_frame_objects(self, sample_log_file):
        j1939_frames = parse_j1939_file(sample_log_file)
        for frame in j1939_frames:
            assert isinstance(frame, J1939Frame)

    def test_ccvs1_frame_decoded(self, sample_log_file):
        j1939_frames = parse_j1939_file(sample_log_file)
        pgns = [f.pgn for f in j1939_frames]
        assert PGN_CCVS1 in pgns

    def test_eec1_frame_decoded(self, sample_log_file):
        j1939_frames = parse_j1939_file(sample_log_file)
        pgns = [f.pgn for f in j1939_frames]
        assert PGN_EEC1 in pgns


class TestIterJ1939Frames:

    def test_yields_j1939_frames(self, sample_log_file):
        frames = list(iter_j1939_frames(sample_log_file))
        assert len(frames) == 3
        for frame in frames:
            assert isinstance(frame, J1939Frame)

    def test_matches_parse_j1939_file(self, sample_log_file):
        list_result = parse_j1939_file(sample_log_file)
        iter_result = list(iter_j1939_frames(sample_log_file))
        assert len(list_result) == len(iter_result)
        for a, b in zip(list_result, iter_result):
            assert a.pgn == b.pgn
            assert a.data == b.data

    def test_large_file_memory_efficiency(self, tmp_path):
        """Verify iter_j1939_frames processes files line-by-line (no full load)."""
        large_log = tmp_path / "large.log"
        lines = [f"(100{i:04d}.000000) vcan0 18FEF100#0000500000000000\n"
                 for i in range(1000)]
        large_log.write_text("".join(lines), encoding="utf-8")

        count = sum(1 for _ in iter_j1939_frames(large_log))
        assert count == 1000
