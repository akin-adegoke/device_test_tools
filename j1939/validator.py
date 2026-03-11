"""J1939 message validation rules.

Validation checks that can be applied to individual frames and sequences of
frames to detect protocol violations and out-of-range sensor readings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .constants import (
    ADDRESS_NULL,
    ADDRESS_GLOBAL,
    PRIORITY_MAX,
    PRIORITY_MIN,
)
from .frame import J1939Frame
from .pgn import get_pgn_info, is_valid_pgn
from .spn import decode_spn, list_spns_for_pgn, is_in_operational_range, SPNValue


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------

class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Severity
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.severity.value}] {self.code}: {self.message}"


@dataclass
class ValidationResult:
    """The aggregated result of validating one J1939 frame."""

    frame: J1939Frame
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when no ERROR-level issues were found."""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class J1939Validator:
    """Apply a set of structural and semantic validation rules to J1939 frames.

    Rules applied (in order):

    1. **V001** – Priority must be in range 0–7.
    2. **V002** – PGN must be a valid 18-bit value.
    3. **V003** – Source address must not be the null address (0xFE) during
       normal communication (allowed only during address claiming).
    4. **V004** – DLC must be consistent with the known PGN's expected length.
    5. **V005** – SPN values must be within their operational ranges.
    6. **V006** – Source address must not equal the destination address.
    7. **V007** – Unknown PGN (INFO-level notice, not an error).
    """

    def validate(self, frame: J1939Frame) -> ValidationResult:
        """Validate *frame* and return a :class:`ValidationResult`."""
        result = ValidationResult(frame=frame)

        self._check_priority(frame, result)
        self._check_pgn(frame, result)
        self._check_source_address(frame, result)
        self._check_dlc(frame, result)
        self._check_spn_ranges(frame, result)
        self._check_address_loopback(frame, result)

        return result

    # ------------------------------------------------------------------
    # Individual rule implementations
    # ------------------------------------------------------------------

    def _check_priority(self, frame: J1939Frame, result: ValidationResult) -> None:
        if not (PRIORITY_MIN <= frame.priority <= PRIORITY_MAX):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="V001",
                    message=(
                        f"Priority {frame.priority} is outside the valid range "
                        f"{PRIORITY_MIN}–{PRIORITY_MAX}"
                    ),
                )
            )

    def _check_pgn(self, frame: J1939Frame, result: ValidationResult) -> None:
        if not is_valid_pgn(frame.pgn):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="V002",
                    message=f"PGN 0x{frame.pgn:X} ({frame.pgn}) exceeds 18-bit range",
                )
            )
            return  # no point checking further PGN rules

        pgn_info = get_pgn_info(frame.pgn)
        if pgn_info is None:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    code="V007",
                    message=f"PGN 0x{frame.pgn:04X} is not in the built-in database",
                )
            )

    def _check_source_address(self, frame: J1939Frame, result: ValidationResult) -> None:
        if frame.source_address == ADDRESS_NULL:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="V003",
                    message=(
                        "Source address 0xFE (null) is only valid during "
                        "address claiming; use a proper node address for data messages"
                    ),
                )
            )

    def _check_dlc(self, frame: J1939Frame, result: ValidationResult) -> None:
        pgn_info = get_pgn_info(frame.pgn)
        if pgn_info is None or pgn_info.expected_length == -1:
            return  # unknown PGN or variable-length → skip length check

        if frame.dlc != pgn_info.expected_length:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="V004",
                    message=(
                        f"DLC {frame.dlc} does not match expected length "
                        f"{pgn_info.expected_length} for PGN {pgn_info.name}"
                    ),
                )
            )

    def _check_spn_ranges(self, frame: J1939Frame, result: ValidationResult) -> None:
        for spn in list_spns_for_pgn(frame.pgn):
            try:
                sv: SPNValue = decode_spn(spn, frame.data)
            except (KeyError, IndexError):
                continue

            if sv.is_error:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="V005",
                        message=f"SPN {spn} ({sv.name}) reports an error indicator",
                    )
                )
            elif sv.is_not_available:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        code="V005",
                        message=f"SPN {spn} ({sv.name}) is not available",
                    )
                )
            elif not is_in_operational_range(sv):
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="V005",
                        message=(
                            f"SPN {spn} ({sv.name}) value {sv.engineering_value} {sv.unit} "
                            f"is outside the operational range"
                        ),
                    )
                )

    def _check_address_loopback(self, frame: J1939Frame, result: ValidationResult) -> None:
        if (
            frame.destination_address != ADDRESS_GLOBAL
            and frame.source_address == frame.destination_address
        ):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="V006",
                    message=(
                        f"Source address 0x{frame.source_address:02X} equals "
                        "the destination address (loopback)"
                    ),
                )
            )
