"""J1939 protocol constants, PGN and SPN definitions."""

# ---------------------------------------------------------------------------
# Address constants
# ---------------------------------------------------------------------------
ADDRESS_NULL = 0xFE          # 254 – used during address claiming
ADDRESS_GLOBAL = 0xFF        # 255 – broadcast / global destination

# ---------------------------------------------------------------------------
# Priority range
# ---------------------------------------------------------------------------
PRIORITY_MIN = 0
PRIORITY_MAX = 7

# ---------------------------------------------------------------------------
# PDU format boundary
# PF < 240  → PDU1 (peer-to-peer, PS = destination address)
# PF >= 240 → PDU2 (broadcast, PS = group extension)
# ---------------------------------------------------------------------------
PDU_FORMAT_PEER_TO_PEER = 0xEF   # inclusive upper bound for PDU1 (239)
PDU_FORMAT_BROADCAST = 0xF0      # inclusive lower bound for PDU2 (240)

# ---------------------------------------------------------------------------
# SPN error / not-available indicators (J1939-71)
# ---------------------------------------------------------------------------
SPN_ERROR_INDICATOR_1BYTE = 0xFE
SPN_NOT_AVAILABLE_1BYTE = 0xFF

SPN_ERROR_INDICATOR_2BYTE = 0xFE00
SPN_NOT_AVAILABLE_2BYTE = 0xFFFF

SPN_ERROR_INDICATOR_4BYTE = 0xFE000000
SPN_NOT_AVAILABLE_4BYTE = 0xFFFFFFFF

# ---------------------------------------------------------------------------
# Known PGNs (decimal / hex for quick reference)
# ---------------------------------------------------------------------------
# Network management
PGN_REQUEST = 0xEA00           # 59904  – Request for PGN
PGN_ACKNOWLEDGEMENT = 0xE800   # 59392  – Acknowledgement (ACK/NACK)
PGN_ADDRESS_CLAIMED = 0xEE00   # 60416  – Address Claimed / Cannot Claim
PGN_COMMANDED_ADDRESS = 0xFED8 # 65240  – Commanded Address

# Transport Protocol
PGN_TP_CM = 0xEC00             # 60416  – TP Connection Management
PGN_TP_DT = 0xEB00             # 60160  – TP Data Transfer

# Engine
PGN_EEC1 = 0xF004              # 61444  – Electronic Engine Controller 1
PGN_EEC2 = 0xF003              # 61443  – Electronic Engine Controller 2
PGN_EEC3 = 0xF002              # 61442  – Electronic Engine Controller 3
PGN_TSC1 = 0x0000              # 0      – Torque/Speed Control 1

# Vehicle motion / speed
PGN_CCVS1 = 0xFEF1             # 65265  – Cruise Control / Vehicle Speed 1

# Fuel
PGN_LFE1 = 0xFEF2              # 65266  – Fuel Economy (Liquid)

# Temperatures / pressures / fluids
PGN_ET1 = 0xFEEE               # 65262  – Engine Temperature 1
PGN_EFL_P1 = 0xFEEF            # 65263  – Engine Fluid Level / Pressure 1
PGN_IC1 = 0xFEED               # 65261  – Inlet / Exhaust Conditions 1

# Electrical
PGN_VEP1 = 0xFEEA              # 65258  – Vehicle Electrical Power 1

# Hours / odometry
PGN_HOURS = 0xFEE5             # 65253  – Engine Hours, Revolutions
PGN_VD = 0xFEE0                # 65248  – Vehicle Distance
PGN_VDHR = 0xFEC1              # 65217  – High-Resolution Vehicle Distance

# Diagnostics
PGN_DM1 = 0xFECA               # 65226  – Active Diagnostic Trouble Codes
PGN_DM2 = 0xFECB               # 65227  – Previously Active DTCs

# ---------------------------------------------------------------------------
# Transport Protocol control byte values (first byte of PGN_TP_CM payload)
# ---------------------------------------------------------------------------
TP_CM_BAM = 0x20               # Broadcast Announce Message
TP_CM_RTS = 0x10               # Request to Send (connection-mode)
TP_CM_CTS = 0x11               # Clear to Send
TP_CM_EOMACK = 0x13            # End of Message Acknowledgement
TP_CM_CONNABORT = 0xFF         # Connection Abort

# ---------------------------------------------------------------------------
# PGN metadata: pgn -> (name, expected_data_length_bytes)
# -1 means variable length
# ---------------------------------------------------------------------------
PGN_INFO: dict[int, tuple[str, int]] = {
    PGN_REQUEST: ("Request", 3),
    PGN_ACKNOWLEDGEMENT: ("Acknowledgement", 8),
    PGN_ADDRESS_CLAIMED: ("Address Claimed", 8),
    PGN_COMMANDED_ADDRESS: ("Commanded Address", 9),
    PGN_TP_CM: ("TP Connection Management", 8),
    PGN_TP_DT: ("TP Data Transfer", 8),
    PGN_EEC1: ("Electronic Engine Controller 1", 8),
    PGN_EEC2: ("Electronic Engine Controller 2", 8),
    PGN_EEC3: ("Electronic Engine Controller 3", 8),
    PGN_CCVS1: ("Cruise Control / Vehicle Speed 1", 8),
    PGN_LFE1: ("Fuel Economy", 8),
    PGN_ET1: ("Engine Temperature 1", 8),
    PGN_EFL_P1: ("Engine Fluid Level / Pressure 1", 8),
    PGN_IC1: ("Inlet / Exhaust Conditions 1", 8),
    PGN_VEP1: ("Vehicle Electrical Power 1", 8),
    PGN_HOURS: ("Engine Hours, Revolutions", 8),
    PGN_VD: ("Vehicle Distance", 8),
    PGN_DM1: ("Active Diagnostic Trouble Codes", -1),
    PGN_DM2: ("Previously Active DTCs", -1),
}

# ---------------------------------------------------------------------------
# SPN definitions
# Format: spn -> SPNDefinition dict keys:
#   name          : human-readable name
#   pgn           : PGN this SPN belongs to
#   byte_offset   : 0-based start byte in the 8-byte payload
#   bit_offset    : 0-based bit offset within the start byte (LSB = 0)
#   length_bits   : total number of bits
#   scale         : multiply raw value by this to get engineering value
#   offset        : add this after scaling
#   unit          : engineering unit string
#   range_min     : minimum valid engineering value
#   range_max     : maximum valid engineering value
# ---------------------------------------------------------------------------
SPN_DEFINITIONS: dict[int, dict] = {
    # EEC1 – Electronic Engine Controller 1 (PGN 61444 / 0xF004)
    190: {
        "name": "Engine Speed",
        "pgn": PGN_EEC1,
        "byte_offset": 3,
        "bit_offset": 0,
        "length_bits": 16,
        "scale": 0.125,
        "offset": 0.0,
        "unit": "rpm",
        "range_min": 0.0,
        "range_max": 8031.875,
    },
    91: {
        "name": "Accelerator Pedal Position 1",
        "pgn": PGN_EEC1,
        "byte_offset": 1,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 0.4,
        "offset": 0.0,
        "unit": "%",
        "range_min": 0.0,
        "range_max": 100.0,
    },
    512: {
        "name": "Driver Demand Engine Percent Torque",
        "pgn": PGN_EEC1,
        "byte_offset": 2,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 1.0,
        "offset": -125.0,
        "unit": "%",
        "range_min": -125.0,
        "range_max": 125.0,
    },
    513: {
        "name": "Actual Engine Percent Torque",
        "pgn": PGN_EEC1,
        "byte_offset": 5,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 1.0,
        "offset": -125.0,
        "unit": "%",
        "range_min": -125.0,
        "range_max": 125.0,
    },
    # CCVS1 – Cruise Control / Vehicle Speed 1 (PGN 65265 / 0xFEF1)
    84: {
        "name": "Wheel-Based Vehicle Speed",
        "pgn": PGN_CCVS1,
        "byte_offset": 1,
        "bit_offset": 0,
        "length_bits": 16,
        "scale": 1 / 256,
        "offset": 0.0,
        "unit": "km/h",
        "range_min": 0.0,
        "range_max": 250.996,
    },
    595: {
        "name": "Cruise Control Active",
        "pgn": PGN_CCVS1,
        "byte_offset": 0,
        "bit_offset": 6,
        "length_bits": 2,
        "scale": 1.0,
        "offset": 0.0,
        "unit": "state",
        "range_min": 0.0,
        "range_max": 3.0,
    },
    # ET1 – Engine Temperature 1 (PGN 65262 / 0xFEEE)
    110: {
        "name": "Engine Coolant Temperature",
        "pgn": PGN_ET1,
        "byte_offset": 0,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 1.0,
        "offset": -40.0,
        "unit": "°C",
        "range_min": -40.0,
        "range_max": 210.0,
    },
    174: {
        "name": "Fuel Temperature",
        "pgn": PGN_ET1,
        "byte_offset": 1,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 1.0,
        "offset": -40.0,
        "unit": "°C",
        "range_min": -40.0,
        "range_max": 210.0,
    },
    175: {
        "name": "Engine Oil Temperature 1",
        "pgn": PGN_ET1,
        "byte_offset": 2,
        "bit_offset": 0,
        "length_bits": 16,
        "scale": 0.03125,
        "offset": -273.0,
        "unit": "°C",
        "range_min": -273.0,
        "range_max": 1734.969,
    },
    # EFL/P1 – Engine Fluid Level / Pressure 1 (PGN 65263 / 0xFEEF)
    94: {
        "name": "Fuel Delivery Pressure",
        "pgn": PGN_EFL_P1,
        "byte_offset": 0,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 4.0,
        "offset": 0.0,
        "unit": "kPa",
        "range_min": 0.0,
        "range_max": 1000.0,
    },
    98: {
        "name": "Engine Oil Level",
        "pgn": PGN_EFL_P1,
        "byte_offset": 2,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 0.4,
        "offset": 0.0,
        "unit": "%",
        "range_min": 0.0,
        "range_max": 100.0,
    },
    100: {
        "name": "Engine Oil Pressure",
        "pgn": PGN_EFL_P1,
        "byte_offset": 3,
        "bit_offset": 0,
        "length_bits": 8,
        "scale": 4.0,
        "offset": 0.0,
        "unit": "kPa",
        "range_min": 0.0,
        "range_max": 1000.0,
    },
    # VEP1 – Vehicle Electrical Power 1 (PGN 65258 / 0xFEEA)
    168: {
        "name": "Battery Potential (Power Input 1)",
        "pgn": PGN_VEP1,
        "byte_offset": 4,
        "bit_offset": 0,
        "length_bits": 16,
        "scale": 0.05,
        "offset": 0.0,
        "unit": "V",
        "range_min": 0.0,
        "range_max": 3212.75,
    },
    # HOURS – Engine Hours, Revolutions (PGN 65253 / 0xFEE5)
    247: {
        "name": "Total Engine Hours",
        "pgn": PGN_HOURS,
        "byte_offset": 0,
        "bit_offset": 0,
        "length_bits": 32,
        "scale": 0.05,
        "offset": 0.0,
        "unit": "h",
        "range_min": 0.0,
        "range_max": 210554060.75,
    },
    # VD – Vehicle Distance (PGN 65248 / 0xFEE0)
    245: {
        "name": "Total Vehicle Distance",
        "pgn": PGN_VD,
        "byte_offset": 4,
        "bit_offset": 0,
        "length_bits": 32,
        "scale": 0.125,
        "offset": 0.0,
        "unit": "km",
        "range_min": 0.0,
        "range_max": 526385151.875,
    },
}
