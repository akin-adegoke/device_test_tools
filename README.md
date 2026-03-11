# device_test_tools

A Python library and full test suite for **J1939 protocol validation**.

J1939 is the higher-layer CAN-bus protocol used in commercial vehicles,
agricultural machinery, construction equipment, and other heavy-duty
applications.

---

## Features

| Module | Description |
|---|---|
| `j1939/frame.py` | Parse 29-bit J1939 CAN identifiers, extract priority / PGN / source address |
| `j1939/pgn.py` | PGN database, PDU1/PDU2 detection, range validation |
| `j1939/spn.py` | SPN signal extraction with scaling, offset, range and error checks |
| `j1939/transport.py` | Transport Protocol (BAM and CMDT) multi-packet reassembly |
| `j1939/decoder.py` | High-level message decoder – produce structured `DecodedMessage` objects |
| `j1939/validator.py` | Rule-based validator with per-issue severity levels (INFO / WARNING / ERROR) |
| `j1939/candump.py` | Parse `candump` log files into `CANFrame` and `J1939Frame` objects |

---

## Quick start

```python
from j1939.frame import CANFrame, J1939Frame
from j1939.decoder import J1939Decoder
from j1939.validator import J1939Validator

# Build a frame (or parse one from a candump log)
raw = CANFrame(can_id=0x18F00400, data=bytes.fromhex("FF007D001900FF00"), is_extended=True)
frame = J1939Frame.from_can_frame(raw)

# Decode
decoder = J1939Decoder()
msg = decoder.decode(frame)
print(msg.pgn_info.name)          # Electronic Engine Controller 1
speed = msg.get_spn(190)
print(speed.engineering_value)    # 800.0  (rpm)

# Validate
validator = J1939Validator()
result = validator.validate(frame)
print(result.is_valid)            # True
print(result.issues)              # []
```

### Parse a candump log file

```python
from j1939.candump import parse_j1939_file
from j1939.decoder import J1939Decoder
from j1939.validator import J1939Validator

frames = parse_j1939_file("my_capture.log")
decoder = J1939Decoder()
validator = J1939Validator()

for frame in frames:
    msg = decoder.decode(frame)
    result = validator.validate(frame)
    if not result.is_valid:
        print(f"PGN 0x{frame.pgn:04X} from SA 0x{frame.source_address:02X}: INVALID")
        for issue in result.errors():
            print(f"  {issue}")
```

### Reassemble multi-packet TP messages

```python
from j1939.transport import TransportProtocolHandler

handler = TransportProtocolHandler()
for frame in j1939_frames:
    result = handler.process(frame)
    if result is not None:
        print(f"Reassembled PGN 0x{result.pgn:04X}: {result.data.hex()}")
```

---

## Supported PGNs

| PGN | Hex | Name |
|---|---|---|
| 61444 | 0xF004 | Electronic Engine Controller 1 (EEC1) |
| 61443 | 0xF003 | Electronic Engine Controller 2 (EEC2) |
| 65265 | 0xFEF1 | Cruise Control / Vehicle Speed 1 (CCVS1) |
| 65262 | 0xFEEE | Engine Temperature 1 (ET1) |
| 65263 | 0xFEEF | Engine Fluid Level / Pressure 1 (EFL/P1) |
| 65258 | 0xFEEA | Vehicle Electrical Power 1 (VEP1) |
| 65253 | 0xFEE5 | Engine Hours, Revolutions |
| 65248 | 0xFEE0 | Vehicle Distance |
| 65226 | 0xFECA | Active Diagnostic Trouble Codes (DM1) |
| 65227 | 0xFECB | Previously Active DTCs (DM2) |
| 59904 | 0xEA00 | Request |
| 59392 | 0xE800 | Acknowledgement |
| 60928 | 0xEE00 | Address Claimed |
| 60416 | 0xEC00 | TP Connection Management |
| 60160 | 0xEB00 | TP Data Transfer |

---

## Supported SPNs

| SPN | Name | Unit | PGN |
|---|---|---|---|
| 190 | Engine Speed | rpm | EEC1 |
| 91 | Accelerator Pedal Position 1 | % | EEC1 |
| 512 | Driver Demand Engine Percent Torque | % | EEC1 |
| 513 | Actual Engine Percent Torque | % | EEC1 |
| 84 | Wheel-Based Vehicle Speed | km/h | CCVS1 |
| 595 | Cruise Control Active | state | CCVS1 |
| 110 | Engine Coolant Temperature | °C | ET1 |
| 174 | Fuel Temperature | °C | ET1 |
| 175 | Engine Oil Temperature 1 | °C | ET1 |
| 94 | Fuel Delivery Pressure | kPa | EFL/P1 |
| 98 | Engine Oil Level | % | EFL/P1 |
| 100 | Engine Oil Pressure | kPa | EFL/P1 |
| 168 | Battery Potential (Power Input 1) | V | VEP1 |
| 247 | Total Engine Hours | h | HOURS |
| 245 | Total Vehicle Distance | km | VD |

---

## Validation rules

| Code | Severity | Description |
|---|---|---|
| V001 | ERROR | Priority out of range (must be 0–7) |
| V002 | ERROR | PGN exceeds 18-bit range |
| V003 | WARNING | Source address is 0xFE (null – only valid during address claiming) |
| V004 | ERROR | DLC does not match expected length for known PGN |
| V005 | WARNING/INFO | SPN value is an error indicator, not available, or out of operational range |
| V006 | ERROR | Source address equals destination address (loopback) |
| V007 | INFO | PGN not found in built-in database |

---

## Running the test suite

```bash
pip install -r requirements.txt
pytest
```

To run a specific test module:

```bash
pytest tests/test_spn.py -v
```

To run with coverage:

```bash
pip install pytest-cov
pytest --cov=j1939 --cov-report=term-missing
```

---

## candump log format

The parser supports the standard `candump` output format:

```
(1609459200.000000) vcan0 18FEF100#0000500000000000
(1609459200.001000) vcan0 18F00400#FF007D001900FF00
```

- **Timestamp**: Unix time in seconds with microsecond precision
- **Interface**: CAN interface name (e.g. `vcan0`, `can0`)
- **CAN ID**: 8 hex digits for 29-bit extended frames, 3 for 11-bit standard
- **Data**: Hex-encoded payload bytes

Lines beginning with `#` are treated as comments and skipped.

---

## Project structure

```
device_test_tools/
├── j1939/                     # Core library
│   ├── __init__.py
│   ├── constants.py           # PGN/SPN definitions and protocol constants
│   ├── frame.py               # CAN frame + J1939 ID parsing
│   ├── pgn.py                 # PGN utilities
│   ├── spn.py                 # SPN signal decoding
│   ├── transport.py           # Transport Protocol (BAM/CMDT)
│   ├── decoder.py             # High-level message decoder
│   ├── validator.py           # Validation rules
│   └── candump.py             # candump log parser
├── tests/                     # Test suite
│   ├── conftest.py            # Shared fixtures
│   ├── test_can_frame.py      # CAN frame + J1939 ID parsing tests
│   ├── test_pgn.py            # PGN utility tests
│   ├── test_spn.py            # SPN decoding tests
│   ├── test_transport_protocol.py  # TP reassembly tests
│   ├── test_decoder.py        # Decoder tests
│   ├── test_validator.py      # Validator tests
│   ├── test_candump.py        # candump parser tests
│   ├── test_address_claiming.py    # Address claiming tests
│   └── test_integration.py   # End-to-end integration tests
├── requirements.txt
├── pytest.ini
└── README.md
```