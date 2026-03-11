"""High-level J1939 message decoder."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List

from .constants import PGN_EEC1, PGN_CCVS1, PGN_ET1, PGN_EFL_P1, PGN_VEP1, PGN_HOURS, PGN_VD
from .frame import J1939Frame
from .pgn import get_pgn_info, PGNInfo
from .spn import decode_spn, list_spns_for_pgn, SPNValue


# ---------------------------------------------------------------------------
# Decoded message result
# ---------------------------------------------------------------------------

@dataclass
class DecodedMessage:
    """Result of decoding a J1939 frame."""

    frame: J1939Frame
    pgn_info: Optional[PGNInfo]
    spn_values: List[SPNValue] = field(default_factory=list)
    decode_errors: List[str] = field(default_factory=list)

    @property
    def pgn(self) -> int:
        return self.frame.pgn

    @property
    def source_address(self) -> int:
        return self.frame.source_address

    @property
    def is_known_pgn(self) -> bool:
        return self.pgn_info is not None

    def get_spn(self, spn: int) -> Optional[SPNValue]:
        """Return the decoded :class:`SPNValue` for *spn*, or ``None``."""
        for sv in self.spn_values:
            if sv.spn == spn:
                return sv
        return None


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------

class J1939Decoder:
    """Decode J1939 frames into structured messages with SPN values."""

    def decode(self, frame: J1939Frame) -> DecodedMessage:
        """Decode a single J1939 frame.

        Always returns a :class:`DecodedMessage`.  Unknown PGNs produce a
        result with an empty ``spn_values`` list and ``pgn_info=None``.
        """
        pgn_info = get_pgn_info(frame.pgn)
        spn_values: list[SPNValue] = []
        errors: list[str] = []

        # Decode all known SPNs for this PGN
        spn_list = list_spns_for_pgn(frame.pgn)
        for spn in spn_list:
            try:
                sv = decode_spn(spn, frame.data)
                spn_values.append(sv)
            except (KeyError, IndexError) as exc:
                errors.append(f"SPN {spn}: {exc}")

        return DecodedMessage(
            frame=frame,
            pgn_info=pgn_info,
            spn_values=spn_values,
            decode_errors=errors,
        )
