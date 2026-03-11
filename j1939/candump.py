"""Parser for candump log files.

candump is a standard Linux tool for logging CAN bus traffic. It produces
two common log formats:

**Standard candump format** (``candump``):

    (1234567890.123456) vcan0 18FEF100#0102030405060708

**Timestamped log format** (``candump -l``):

    (1234567890.123456) vcan0 18FEF100#0102030405060708

Both formats are handled by this parser.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Generator, List, Optional

from .frame import CANFrame, J1939Frame


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches lines like:
#   (1234567890.123456) vcan0 18FEF100#0102030405060708
# Extended IDs use 8 hex digits; standard 11-bit use 3.
_LINE_PATTERN = re.compile(
    r"^\s*"
    r"\((?P<timestamp>[0-9]+\.[0-9]+)\)"      # (timestamp)
    r"\s+"
    r"(?P<interface>[A-Za-z0-9_]+)"            # interface name
    r"\s+"
    r"(?P<can_id>[0-9A-Fa-f]{3,8})"           # CAN ID (3 or 8 hex digits)
    r"#"
    r"(?P<data>[0-9A-Fa-f]*)"                  # data bytes (may be empty)
    r"\s*$"
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_line(line: str) -> Optional[CANFrame]:
    """Parse a single candump log line into a :class:`CANFrame`.

    Returns ``None`` for blank lines and comment lines (starting with ``#``).

    Args:
        line: A single line from a candump log file.

    Returns:
        :class:`CANFrame` or ``None``.

    Raises:
        ValueError: if the line is non-empty and cannot be parsed.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    m = _LINE_PATTERN.match(stripped)
    if not m:
        raise ValueError(f"Cannot parse candump line: {line!r}")

    timestamp = float(m.group("timestamp"))
    interface = m.group("interface")
    can_id_str = m.group("can_id")
    data_str = m.group("data")

    can_id = int(can_id_str, 16)
    # 29-bit (extended) IDs are written as 8 hex digits; 11-bit as 3
    is_extended = len(can_id_str) == 8

    data = bytes.fromhex(data_str) if data_str else b""

    return CANFrame(
        can_id=can_id,
        data=data,
        timestamp=timestamp,
        is_extended=is_extended,
        interface=interface,
    )


def parse_file(path: str | Path) -> List[CANFrame]:
    """Parse an entire candump log file and return all :class:`CANFrame` objects.

    Args:
        path: Path to the candump log file.

    Returns:
        List of :class:`CANFrame` objects in file order.

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError: if any non-comment, non-empty line cannot be parsed.
    """
    path = Path(path)
    frames: list[CANFrame] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            try:
                frame = parse_line(line)
            except ValueError as exc:
                raise ValueError(f"Line {lineno}: {exc}") from exc
            if frame is not None:
                frames.append(frame)
    return frames


def parse_j1939_file(path: str | Path) -> List[J1939Frame]:
    """Parse a candump log file and return only the J1939 (extended) frames.

    Standard-frame (11-bit) CAN messages are silently skipped.

    Args:
        path: Path to the candump log file.

    Returns:
        List of :class:`J1939Frame` objects.
    """
    raw_frames = parse_file(path)
    j1939_frames: list[J1939Frame] = []
    for frame in raw_frames:
        if frame.is_extended:
            try:
                j1939_frames.append(J1939Frame.from_can_frame(frame))
            except ValueError:
                pass
    return j1939_frames


def iter_j1939_frames(path: str | Path) -> Generator[J1939Frame, None, None]:
    """Lazily yield :class:`J1939Frame` objects from a candump log file.

    Memory-efficient alternative to :func:`parse_j1939_file` for large files.

    Args:
        path: Path to the candump log file.

    Yields:
        :class:`J1939Frame` objects.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            try:
                frame = parse_line(line)
            except ValueError as exc:
                raise ValueError(f"Line {lineno}: {exc}") from exc
            if frame is not None and frame.is_extended:
                try:
                    yield J1939Frame.from_can_frame(frame)
                except ValueError:
                    pass
