"""J1939 protocol validation library.

Quick start::

    from j1939.frame import CANFrame, J1939Frame
    from j1939.decoder import J1939Decoder
    from j1939.validator import J1939Validator

    frame = CANFrame(can_id=0x18FEF100, data=bytes.fromhex("0000FA7D000000FF"))
    j1939 = J1939Frame.from_can_frame(frame)

    decoder = J1939Decoder()
    msg = decoder.decode(j1939)
    print(msg.spn_values)

    validator = J1939Validator()
    result = validator.validate(j1939)
    print(result.is_valid, result.issues)
"""

from .frame import CANFrame, J1939Frame, parse_j1939_id, compute_pgn, build_j1939_id
from .pgn import get_pgn_info, is_pdu1, is_pdu2, is_valid_pgn
from .spn import decode_spn, extract_bits, get_spn_definition, list_spns_for_pgn, is_in_operational_range
from .decoder import J1939Decoder, DecodedMessage
from .validator import J1939Validator, ValidationResult, ValidationIssue, Severity
from .transport import TransportProtocolHandler, TPSession, TPResult
from .candump import parse_line, parse_file, parse_j1939_file, iter_j1939_frames

__all__ = [
    # frame
    "CANFrame",
    "J1939Frame",
    "parse_j1939_id",
    "compute_pgn",
    "build_j1939_id",
    # pgn
    "get_pgn_info",
    "is_pdu1",
    "is_pdu2",
    "is_valid_pgn",
    # spn
    "decode_spn",
    "extract_bits",
    "get_spn_definition",
    "list_spns_for_pgn",
    "is_in_operational_range",
    # decoder
    "J1939Decoder",
    "DecodedMessage",
    # validator
    "J1939Validator",
    "ValidationResult",
    "ValidationIssue",
    "Severity",
    # transport
    "TransportProtocolHandler",
    "TPSession",
    "TPResult",
    # candump
    "parse_line",
    "parse_file",
    "parse_j1939_file",
    "iter_j1939_frames",
]
