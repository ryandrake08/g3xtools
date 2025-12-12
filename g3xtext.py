#!/usr/bin/env python3
"""
G3X Text Out Parser

Parses RS-232 "Text Out" format data from Garmin G3X/G3X Touch displays as defined
in Appendix C of the G3X Installation Manual (190-01115-01 Rev. AW).

Usage:
    g3xtext /dev/ttyUSB0              # Read from serial port
    g3xtext --file g3x_flight.log     # Read from file
    g3xtext -v /dev/ttyUSB0           # Verbose output
    g3xtext --filter attitude,engine /dev/ttyUSB0

Serial port settings (fixed per spec):
    - Baud rate: 115,200
    - Data bits: 8
    - Stop bits: 1
    - Parity: None
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol, Union

# Serial port settings (fixed per G3X spec - not configurable)
BAUD_RATE = 115200
DATA_BITS = 8
STOP_BITS = 1
PARITY = "N"

# Message escape characters
ESCAPE_STANDARD = ord("=")  # 0x3D
ESCAPE_GPS_PVT = ord("@")  # 0x40

# Invalid data indicator
INVALID_CHAR = ord("_")  # 0x5F


# =============================================================================
# Exceptions
# =============================================================================


class G3XTextError(Exception):
    """Base exception for g3xtext errors."""

    pass


class ChecksumError(G3XTextError):
    """Checksum validation failed."""

    pass


class ParseError(G3XTextError):
    """Message format invalid or unparseable."""

    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AttitudeAirData:
    """Attitude and air data (message ID '1', ~10 Hz)."""

    timestamp: datetime  # UTC time from message
    pitch: Optional[float]  # degrees, positive = up
    roll: Optional[float]  # degrees, positive = right
    heading: Optional[int]  # degrees magnetic (0-359)
    airspeed: Optional[float]  # knots (indicated)
    pressure_altitude: Optional[int]  # feet
    rate_of_turn: Optional[float]  # degrees/sec, positive = right
    lateral_accel: Optional[float]  # G, positive = leftward
    vertical_accel: Optional[float]  # G, positive = upward
    aoa: Optional[int]  # 0-99 (0=below min, 60=warning, 99=stall)
    vertical_speed: Optional[int]  # fpm, positive = up
    oat: Optional[int]  # degrees Celsius
    altimeter_setting: Optional[float]  # inHg


@dataclass
class AttitudeAirDataSet2:
    """Attitude and air data set 2 (message ID '2', ~2 Hz)."""

    timestamp: datetime
    true_airspeed: Optional[float]  # knots
    density_altitude: Optional[int]  # feet
    heading_bug: Optional[int]  # degrees magnetic (0-359)
    altitude_bug: Optional[int]  # feet
    airspeed_bug: Optional[float]  # knots
    vertical_speed_bug: Optional[int]  # fpm, positive = up


@dataclass
class EngineData:
    """Engine and airframe data (message ID '3', ~5 Hz)."""

    timestamp: datetime
    oil_pressure: Optional[int]  # PSI
    oil_temperature: Optional[int]  # degrees Celsius
    rpm: Optional[int]  # RPM
    manifold_pressure: Optional[float]  # inHg
    fuel_flow: Optional[float]  # gallons/hour
    fuel_pressure: Optional[float]  # PSI
    fuel_quantity_1: Optional[float]  # gallons
    fuel_quantity_2: Optional[float]  # gallons
    fuel_quantity_3: Optional[float]  # gallons
    fuel_quantity_4: Optional[float]  # gallons
    calculated_fuel: Optional[float]  # gallons (from fuel computer)
    volts_1: Optional[float]  # Volts
    volts_2: Optional[float]  # Volts
    amps_1: Optional[float]  # Amps
    amps_2: Optional[float]  # Amps
    total_aircraft_time: Optional[float]  # hours
    engine_time: Optional[float]  # hours
    cht: tuple[
        Optional[int],
        Optional[int],
        Optional[int],
        Optional[int],
        Optional[int],
        Optional[int],
    ]  # degrees C, cylinders 1-6
    egt: tuple[
        Optional[int],
        Optional[int],
        Optional[int],
        Optional[int],
        Optional[int],
        Optional[int],
    ]  # degrees C, cylinders 1-6
    tit_1: Optional[int]  # degrees Celsius
    tit_2: Optional[int]  # degrees Celsius
    elevator_trim: Optional[float]  # percent (0=up, 50=neutral, 100=down)
    flap_position: Optional[int]  # degrees
    carb_temp: Optional[float]  # degrees Celsius
    coolant_pressure: Optional[float]  # PSI
    coolant_temp: Optional[float]  # degrees Celsius
    aileron_trim: Optional[float]  # percent (0=left, 50=neutral, 100=right)
    rudder_trim: Optional[float]  # percent (0=left, 50=neutral, 100=right)
    discrete_inputs: tuple[bool, bool, bool, bool]  # inputs 1-4


@dataclass
class GpsPvt:
    """GPS position, velocity, time (message '@', ~1 Hz)."""

    timestamp: datetime  # UTC time from message
    latitude: Optional[float]  # decimal degrees, positive = north
    longitude: Optional[float]  # decimal degrees, positive = east
    position_status: Optional[str]  # 'g'=2D, 'G'=3D, 'd'=2D diff, 'D'=3D diff, 'S'=sim
    horizontal_error: Optional[int]  # meters
    altitude_msl: Optional[int]  # meters
    velocity_east: Optional[float]  # m/s, positive = east
    velocity_north: Optional[float]  # m/s, positive = north
    velocity_vertical: Optional[float]  # m/s, positive = up


@dataclass
class GpsData:
    """GPS supplemental data (message ID '7', ~1 Hz)."""

    timestamp: datetime
    height_agl: Optional[int]  # feet (resolution: 100 ft)
    ground_speed: Optional[float]  # knots


@dataclass
class EisParameterInfo:
    """EIS parameter definition from info message."""

    parameter_id: int  # 0x00-0xFF
    units: str  # '0'=none, 'C'=Celsius, 'P'=Pascals, 'L'=Liters, 'V'=Volts, 'A'=Amps, 'l'=L/s
    name: str  # up to 16 characters


@dataclass
class EisDiscreteData:
    """EIS discrete parameter values (message ID '5D')."""

    timestamp: datetime
    parameters: dict[int, bool]  # parameter_id -> active (True) or inactive (False)


@dataclass
class EisNumericData:
    """EIS numeric parameter values (message ID '51' or '52')."""

    timestamp: datetime
    engine: int  # 1 or 2
    parameters: dict[int, Optional[float]]  # parameter_id -> value (None if invalid)


@dataclass
class CniData:
    """Communication, navigation, identification data (message ID 'C', ~1 Hz)."""

    timestamp: datetime
    # COM1
    com1_active_freq: Optional[int]  # kHz (118000-136990)
    com1_standby_freq: Optional[int]  # kHz
    com1_status: Optional[str]  # 'T'=transmit, 'M'=monitor, 'R'=receive, None=no activity
    com1_monitor_enabled: Optional[bool]
    com1_fail: Optional[bool]
    com1_squelch_bypass: Optional[bool]
    com1_volume: Optional[int]  # 0-100
    # COM2
    com2_active_freq: Optional[int]  # kHz
    com2_standby_freq: Optional[int]  # kHz
    com2_status: Optional[str]
    com2_monitor_enabled: Optional[bool]
    com2_fail: Optional[bool]
    com2_squelch_bypass: Optional[bool]
    com2_volume: Optional[int]
    # Navigation source
    nav_source: Optional[str]  # 'I'=internal GPS, 'G'=GPS1, 'g'=GPS2, 'V'=VLOC1, 'v'=VLOC2
    # NAV1
    nav1_active_freq: Optional[int]  # kHz (108000-117975)
    nav1_standby_freq: Optional[int]  # kHz
    nav1_ident: Optional[str]  # up to 10 characters
    nav1_fail: Optional[bool]
    nav1_volume: Optional[int]  # 0-100
    # NAV2
    nav2_active_freq: Optional[int]  # kHz
    nav2_standby_freq: Optional[int]  # kHz
    nav2_ident: Optional[str]
    nav2_fail: Optional[bool]
    nav2_volume: Optional[int]
    # Audio panel
    audio_com1_rx: Optional[bool]
    audio_com2_rx: Optional[bool]
    audio_com1_tx: Optional[bool]
    audio_com2_tx: Optional[bool]
    audio_nav1_rx: Optional[bool]
    audio_nav2_rx: Optional[bool]
    audio_intercom_isolate: Optional[str]  # '0'=none, 'P'=pilot, 'C'=crew
    audio_marker_beacon: Optional[str]  # 'n'=none, 'o'=outer, 'm'=middle, 'i'=inner
    audio_panel_fail: Optional[bool]
    # Transponder
    transponder_mode: Optional[str]  # 'N'=on, 'A'=alt, 'S'=standby, 'G'=ground
    transponder_code: Optional[int]  # 0000-7777 (octal display, stored as int)
    transponder_ident: Optional[bool]
    transponder_reply: Optional[bool]
    transponder_flight_id: Optional[str]  # up to 8 characters
    transponder_fail: Optional[bool]


# Type alias for all message types
G3XMessage = Union[
    AttitudeAirData,
    AttitudeAirDataSet2,
    EngineData,
    GpsPvt,
    GpsData,
    EisParameterInfo,
    EisDiscreteData,
    EisNumericData,
    CniData,
]


# =============================================================================
# Handler Protocol
# =============================================================================


class G3XTextHandler(Protocol):
    """Protocol for receiving parsed G3X Text Out messages."""

    def on_attitude_air_data(self, data: AttitudeAirData) -> None:
        """Called when Attitude/Air Data message (ID '1') is received."""
        ...

    def on_attitude_air_data_set2(self, data: AttitudeAirDataSet2) -> None:
        """Called when Attitude/Air Data Set 2 message (ID '2') is received."""
        ...

    def on_engine_data(self, data: EngineData) -> None:
        """Called when Engine Data message (ID '3') is received."""
        ...

    def on_gps_pvt(self, data: GpsPvt) -> None:
        """Called when GPS PVT message ('@') is received."""
        ...

    def on_gps_data(self, data: GpsData) -> None:
        """Called when GPS Data message (ID '7') is received."""
        ...

    def on_eis_parameter_info(self, data: list[EisParameterInfo]) -> None:
        """Called when EIS Parameter Information message (ID '5i') is received."""
        ...

    def on_eis_discrete_data(self, data: EisDiscreteData) -> None:
        """Called when EIS Discrete Parameter Data message (ID '5D') is received."""
        ...

    def on_eis_numeric_data(self, data: EisNumericData) -> None:
        """Called when EIS Numeric Parameter Data message (ID '51'/'52') is received."""
        ...

    def on_cni_data(self, data: CniData) -> None:
        """Called when CNI message (ID 'C') is received."""
        ...


# =============================================================================
# Core Parsing Functions
# =============================================================================


def calculate_checksum(data: bytes) -> int:
    """Calculate 8-bit checksum (simple sum of bytes, truncated to 8 bits)."""
    return sum(data) & 0xFF


def verify_checksum(data: bytes) -> bool:
    """
    Verify checksum for a standard '=' message.

    The last 4 bytes before CR/LF are: 2-char hex checksum + CR + LF
    The checksum covers all bytes from the start up to (but not including) the checksum.

    Args:
        data: Complete message including CR/LF

    Returns:
        True if checksum is valid

    Raises:
        ParseError: If message format is invalid for checksum verification
    """
    if len(data) < 6:  # Minimum: = + ID + checksum(2) + CR + LF
        raise ParseError(f"Message too short for checksum verification: {len(data)} bytes")

    if not data.endswith(b"\r\n"):
        raise ParseError("Message does not end with CR/LF")

    # Extract checksum hex string (2 bytes before CR/LF)
    checksum_hex = data[-4:-2]

    try:
        expected_checksum = int(checksum_hex, 16)
    except ValueError as e:
        raise ParseError(f"Invalid checksum hex value: {checksum_hex!r}") from e

    # Calculate checksum over all bytes before the checksum
    actual_checksum = calculate_checksum(data[:-4])

    if actual_checksum != expected_checksum:
        raise ChecksumError(f"Checksum mismatch: expected 0x{expected_checksum:02X}, got 0x{actual_checksum:02X}")

    return True


def has_invalid_data(field: bytes) -> bool:
    """Check if a field contains invalid data indicators (underscores)."""
    return INVALID_CHAR in field


def parse_int_field(data: bytes, offset: int, width: int) -> Optional[int]:
    """
    Parse an integer field from fixed-width data.

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes
        width: Width of field in bytes

    Returns:
        Parsed integer, or None if field contains invalid data
    """
    field = data[offset : offset + width]
    if has_invalid_data(field):
        return None

    try:
        return int(field)
    except ValueError as e:
        raise ParseError(f"Invalid integer at offset {offset}: {field!r}") from e


def parse_signed_int_field(data: bytes, offset: int, width: int) -> Optional[int]:
    """
    Parse a signed integer field (with +/- prefix) from fixed-width data.

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes
        width: Width of field in bytes (including sign)

    Returns:
        Parsed signed integer, or None if field contains invalid data
    """
    field = data[offset : offset + width]
    if has_invalid_data(field):
        return None

    try:
        return int(field)
    except ValueError as e:
        raise ParseError(f"Invalid signed integer at offset {offset}: {field!r}") from e


def parse_scaled_field(data: bytes, offset: int, width: int, scale: float, signed: bool = False) -> Optional[float]:
    """
    Parse a numeric field and apply scaling factor.

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes
        width: Width of field in bytes
        scale: Scaling factor to apply (e.g., 0.1 for tenths)
        signed: Whether the field is signed

    Returns:
        Scaled float value, or None if field contains invalid data
    """
    raw = parse_signed_int_field(data, offset, width) if signed else parse_int_field(data, offset, width)

    if raw is None:
        return None
    return raw * scale


def parse_char_field(data: bytes, offset: int) -> Optional[str]:
    """
    Parse a single character field.

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes

    Returns:
        Single character string, or None if field is underscore
    """
    char = data[offset : offset + 1]
    if char == b"_":
        return None
    return char.decode("ascii")


def parse_string_field(data: bytes, offset: int, width: int) -> Optional[str]:
    """
    Parse a fixed-width string field.

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes
        width: Width of field in bytes

    Returns:
        String value (stripped of trailing nulls/spaces), or None if all underscores
    """
    field = data[offset : offset + width]

    # Check if entire field is underscores
    if all(b == INVALID_CHAR for b in field):
        return None

    # Decode and strip trailing nulls/spaces
    return field.decode("ascii").rstrip("\x00 ")


def parse_bool_field(data: bytes, offset: int) -> Optional[bool]:
    """
    Parse a boolean field (0/1).

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes

    Returns:
        Boolean value, or None if field is underscore
    """
    char = data[offset : offset + 1]
    if char == b"_":
        return None
    if char == b"1":
        return True
    if char == b"0":
        return False
    raise ParseError(f"Invalid boolean value at offset {offset}: {char!r}")


def parse_timestamp(data: bytes, offset: int, include_date: bool = False) -> datetime:
    """
    Parse UTC timestamp from message.

    Args:
        data: Raw message bytes
        offset: Starting offset in bytes
        include_date: If True, parse YYMMDD before HHMMSS (GPS PVT format)

    Returns:
        datetime in UTC

    Raises:
        ParseError: If timestamp format is invalid
    """
    try:
        if include_date:
            # GPS PVT format: YYMMDDHHMMSS (12 chars)
            year = int(data[offset : offset + 2])
            month = int(data[offset + 2 : offset + 4])
            day = int(data[offset + 4 : offset + 6])
            hour = int(data[offset + 6 : offset + 8])
            minute = int(data[offset + 8 : offset + 10])
            second = int(data[offset + 10 : offset + 12])
            # Convert 2-digit year to 4-digit (assume 2000s for aviation)
            year = 2000 + year
            return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        else:
            # Standard format: HHMMSSFF (8 chars, FF = centiseconds)
            hour = int(data[offset : offset + 2])
            minute = int(data[offset + 2 : offset + 4])
            second = int(data[offset + 4 : offset + 6])
            centisecond = int(data[offset + 6 : offset + 8])
            # Use today's date with the time
            now = datetime.now(timezone.utc)
            return datetime(
                now.year,
                now.month,
                now.day,
                hour,
                minute,
                second,
                centisecond * 10000,  # Convert centiseconds to microseconds
                tzinfo=timezone.utc,
            )
    except (ValueError, IndexError) as e:
        raise ParseError(f"Invalid timestamp at offset {offset}") from e


def identify_message_type(data: bytes) -> tuple[str, int]:
    """
    Identify message type from raw data.

    Args:
        data: Raw message bytes

    Returns:
        Tuple of (message_type, version) where message_type is:
        - '1': Attitude/Air Data
        - '2': Attitude/Air Data Set 2
        - '3': Engine Data
        - '5i': EIS Parameter Information
        - '5D': EIS Discrete Parameter Data
        - '51': EIS Numeric Parameter Data (Engine 1)
        - '52': EIS Numeric Parameter Data (Engine 2)
        - '7': GPS Data
        - 'C': CNI
        - '@': GPS PVT

    Raises:
        ParseError: If message type cannot be identified
    """
    if len(data) < 2:
        raise ParseError("Message too short to identify type")

    escape = data[0]

    if escape == ESCAPE_GPS_PVT:
        # GPS PVT message (no version)
        return ("@", 0)

    if escape != ESCAPE_STANDARD:
        raise ParseError(f"Unknown escape character: 0x{escape:02X}")

    if len(data) < 3:
        raise ParseError("Message too short to identify type and version")

    msg_id = chr(data[1])
    version = int(chr(data[2]))

    # Handle EIS sub-types
    if msg_id == "5":
        if len(data) < 4:
            raise ParseError("EIS message too short to identify sub-type")
        sub_id = chr(data[3])
        return (f"5{sub_id}", version)

    return (msg_id, version)


def parse_scientific_notation(value_str: str) -> Optional[float]:
    """
    Parse EIS numeric value in scientific notation (±X.XXXXE±XX).

    Args:
        value_str: 11-character string in format ±X.XXXXE±XX

    Returns:
        Float value, or None if all underscores
    """
    if "_" in value_str:
        return None

    try:
        return float(value_str)
    except ValueError as e:
        raise ParseError(f"Invalid scientific notation: {value_str!r}") from e


# =============================================================================
# Message Parsers
# =============================================================================


def parse_attitude_air_data(data: bytes) -> AttitudeAirData:
    """
    Parse Attitude/Air Data message (ID '1').

    Expected length: 59 bytes
    """
    if len(data) != 59:
        raise ParseError(f"Attitude/Air Data message wrong length: {len(data)} (expected 59)")

    verify_checksum(data)

    timestamp = parse_timestamp(data, 3)

    # Pitch: offset 11, width 4, 0.1 degree, signed
    pitch = parse_scaled_field(data, 11, 4, 0.1, signed=True)

    # Roll: offset 15, width 5, 0.1 degree, signed
    roll = parse_scaled_field(data, 15, 5, 0.1, signed=True)

    # Heading: offset 20, width 3, 1 degree, unsigned
    heading = parse_int_field(data, 20, 3)

    # Airspeed: offset 23, width 4, 0.1 knots, unsigned
    airspeed = parse_scaled_field(data, 23, 4, 0.1, signed=False)

    # Pressure altitude: offset 27, width 6, 1 foot, signed
    pressure_altitude = parse_signed_int_field(data, 27, 6)

    # Rate of turn: offset 33, width 4, 0.1 degree/sec, signed
    rate_of_turn = parse_scaled_field(data, 33, 4, 0.1, signed=True)

    # Lateral acceleration: offset 37, width 3, 0.01 G, signed
    lateral_accel = parse_scaled_field(data, 37, 3, 0.01, signed=True)

    # Vertical acceleration: offset 40, width 3, 0.1 G, signed
    vertical_accel = parse_scaled_field(data, 40, 3, 0.1, signed=True)

    # AOA: offset 43, width 2, unsigned
    aoa = parse_int_field(data, 43, 2)

    # Vertical speed: offset 45, width 4, 10 fpm, signed
    vs_raw = parse_signed_int_field(data, 45, 4)
    vertical_speed = vs_raw * 10 if vs_raw is not None else None

    # OAT: offset 49, width 3, 1 degree C, signed
    oat = parse_signed_int_field(data, 49, 3)

    # Altimeter setting: offset 52, width 3, 0.01 inHg offset from 27.50
    altimeter_raw = parse_int_field(data, 52, 3)
    altimeter_setting = (altimeter_raw * 0.01 + 27.50) if altimeter_raw is not None else None

    return AttitudeAirData(
        timestamp=timestamp,
        pitch=pitch,
        roll=roll,
        heading=heading,
        airspeed=airspeed,
        pressure_altitude=pressure_altitude,
        rate_of_turn=rate_of_turn,
        lateral_accel=lateral_accel,
        vertical_accel=vertical_accel,
        aoa=aoa,
        vertical_speed=vertical_speed,
        oat=oat,
        altimeter_setting=altimeter_setting,
    )


def parse_attitude_air_data_set2(data: bytes) -> AttitudeAirDataSet2:
    """
    Parse Attitude/Air Data Set 2 message (ID '2').

    Expected length: 42 bytes
    """
    if len(data) != 42:
        raise ParseError(f"Attitude/Air Data Set 2 message wrong length: {len(data)} (expected 42)")

    verify_checksum(data)

    timestamp = parse_timestamp(data, 3)

    # True airspeed: offset 11, width 4, 0.1 knots
    true_airspeed = parse_scaled_field(data, 11, 4, 0.1, signed=False)

    # Density altitude: offset 15, width 6, 1 foot, signed
    density_altitude = parse_signed_int_field(data, 15, 6)

    # Heading bug: offset 21, width 3, 1 degree
    heading_bug = parse_int_field(data, 21, 3)

    # Altitude bug: offset 24, width 6, 1 foot, signed
    altitude_bug = parse_signed_int_field(data, 24, 6)

    # Airspeed bug: offset 30, width 4, 0.1 knots
    airspeed_bug = parse_scaled_field(data, 30, 4, 0.1, signed=False)

    # Vertical speed bug: offset 34, width 4, 10 fpm, signed
    vs_raw = parse_signed_int_field(data, 34, 4)
    vertical_speed_bug = vs_raw * 10 if vs_raw is not None else None

    return AttitudeAirDataSet2(
        timestamp=timestamp,
        true_airspeed=true_airspeed,
        density_altitude=density_altitude,
        heading_bug=heading_bug,
        altitude_bug=altitude_bug,
        airspeed_bug=airspeed_bug,
        vertical_speed_bug=vertical_speed_bug,
    )


def parse_engine_data(data: bytes) -> EngineData:
    """
    Parse Engine Data message (ID '3').

    Expected length: 221 bytes
    """
    if len(data) != 221:
        raise ParseError(f"Engine Data message wrong length: {len(data)} (expected 221)")

    verify_checksum(data)

    timestamp = parse_timestamp(data, 3)

    # Oil pressure: offset 11, width 3, 1 PSI
    oil_pressure = parse_int_field(data, 11, 3)

    # Oil temperature: offset 14, width 4, 1 degree C, signed
    oil_temperature = parse_signed_int_field(data, 14, 4)

    # RPM: offset 18, width 4
    rpm = parse_int_field(data, 18, 4)

    # Unused: offset 22, width 4

    # Manifold pressure: offset 26, width 3, 0.1 inHg
    manifold_pressure = parse_scaled_field(data, 26, 3, 0.1, signed=False)

    # Fuel flow: offset 29, width 3, 0.1 gph
    fuel_flow = parse_scaled_field(data, 29, 3, 0.1, signed=False)

    # Unused: offset 32, width 3

    # Fuel pressure: offset 35, width 3, 0.1 PSI
    fuel_pressure = parse_scaled_field(data, 35, 3, 0.1, signed=False)

    # Fuel quantity 1: offset 38, width 3, 0.1 gallon
    fuel_quantity_1 = parse_scaled_field(data, 38, 3, 0.1, signed=False)

    # Fuel quantity 2: offset 41, width 3, 0.1 gallon
    fuel_quantity_2 = parse_scaled_field(data, 41, 3, 0.1, signed=False)

    # Calculated fuel: offset 44, width 3, 0.1 gallon
    calculated_fuel = parse_scaled_field(data, 44, 3, 0.1, signed=False)

    # Volts 1: offset 47, width 3, 0.1 V
    volts_1 = parse_scaled_field(data, 47, 3, 0.1, signed=False)

    # Volts 2: offset 50, width 3, 0.1 V
    volts_2 = parse_scaled_field(data, 50, 3, 0.1, signed=False)

    # Amps 1: offset 53, width 4, 0.1 A, signed
    amps_1 = parse_scaled_field(data, 53, 4, 0.1, signed=True)

    # Total aircraft time: offset 57, width 5, 0.1 hour
    total_aircraft_time = parse_scaled_field(data, 57, 5, 0.1, signed=False)

    # Engine time: offset 62, width 5, 0.1 hour
    engine_time = parse_scaled_field(data, 62, 5, 0.1, signed=False)

    # CHT/EGT are stored in reverse order (6,5,4,3,2,1) in the message
    # CHT6: offset 67, EGT6: 71, CHT5: 75, EGT5: 79, etc.
    cht6 = parse_signed_int_field(data, 67, 4)
    egt6 = parse_signed_int_field(data, 71, 4)
    cht5 = parse_signed_int_field(data, 75, 4)
    egt5 = parse_signed_int_field(data, 79, 4)
    cht4 = parse_signed_int_field(data, 83, 4)
    egt4 = parse_signed_int_field(data, 87, 4)
    cht3 = parse_signed_int_field(data, 91, 4)
    egt3 = parse_signed_int_field(data, 95, 4)
    cht2 = parse_signed_int_field(data, 99, 4)
    egt2 = parse_signed_int_field(data, 103, 4)
    cht1 = parse_signed_int_field(data, 107, 4)
    egt1 = parse_signed_int_field(data, 111, 4)

    # TIT1: offset 115, width 4, signed
    tit_1 = parse_signed_int_field(data, 115, 4)

    # TIT2: offset 119, width 4, signed
    tit_2 = parse_signed_int_field(data, 119, 4)

    # Elevator trim: offset 123, width 5, 1% of travel, signed (though spec says +0000 to +0100)
    elevator_trim = parse_scaled_field(data, 123, 5, 1.0, signed=True)

    # Units indicator 'T': offset 128

    # Flap position: offset 129, width 5, 1 degree, signed
    flap_position = parse_signed_int_field(data, 129, 5)

    # Units indicator 'T': offset 134

    # Carb temp: offset 135, width 5, 0.1 degree C, signed
    carb_temp = parse_scaled_field(data, 135, 5, 0.1, signed=True)

    # Units indicator 'C': offset 140

    # Coolant pressure: offset 141, width 5, 0.01 PSI
    coolant_pressure = parse_scaled_field(data, 141, 5, 0.01, signed=False)

    # Units indicator 'P': offset 146

    # Coolant temperature: offset 147, width 5, 0.1 degree C, signed
    coolant_temp = parse_scaled_field(data, 147, 5, 0.1, signed=True)

    # Units indicator 'C': offset 152

    # Amps 2: offset 153, width 5, 0.1 A, signed
    amps_2 = parse_scaled_field(data, 153, 5, 0.1, signed=True)

    # Units indicator 'A': offset 158

    # Aileron trim: offset 159, width 5, 1% of travel
    aileron_trim = parse_scaled_field(data, 159, 5, 1.0, signed=True)

    # Units indicator 'T': offset 164

    # Rudder trim: offset 165, width 5, 1% of travel
    rudder_trim = parse_scaled_field(data, 165, 5, 1.0, signed=True)

    # Units indicator 'T': offset 170

    # Fuel quantity 3: offset 171, width 5, 0.1 gallon
    fuel_quantity_3 = parse_scaled_field(data, 171, 5, 0.1, signed=True)

    # Units indicator 'G': offset 176

    # Fuel quantity 4: offset 177, width 5, 0.1 gallon
    fuel_quantity_4 = parse_scaled_field(data, 177, 5, 0.1, signed=True)

    # Units indicator 'G': offset 182

    # Unused: offset 183, width 18

    # Discrete inputs: offset 201-204
    discrete_1 = parse_bool_field(data, 201)
    discrete_2 = parse_bool_field(data, 202)
    discrete_3 = parse_bool_field(data, 203)
    discrete_4 = parse_bool_field(data, 204)

    return EngineData(
        timestamp=timestamp,
        oil_pressure=oil_pressure,
        oil_temperature=oil_temperature,
        rpm=rpm,
        manifold_pressure=manifold_pressure,
        fuel_flow=fuel_flow,
        fuel_pressure=fuel_pressure,
        fuel_quantity_1=fuel_quantity_1,
        fuel_quantity_2=fuel_quantity_2,
        fuel_quantity_3=fuel_quantity_3,
        fuel_quantity_4=fuel_quantity_4,
        calculated_fuel=calculated_fuel,
        volts_1=volts_1,
        volts_2=volts_2,
        amps_1=amps_1,
        amps_2=amps_2,
        total_aircraft_time=total_aircraft_time,
        engine_time=engine_time,
        cht=(cht1, cht2, cht3, cht4, cht5, cht6),
        egt=(egt1, egt2, egt3, egt4, egt5, egt6),
        tit_1=tit_1,
        tit_2=tit_2,
        elevator_trim=elevator_trim,
        flap_position=flap_position,
        carb_temp=carb_temp,
        coolant_pressure=coolant_pressure,
        coolant_temp=coolant_temp,
        aileron_trim=aileron_trim,
        rudder_trim=rudder_trim,
        discrete_inputs=(
            discrete_1 if discrete_1 is not None else False,
            discrete_2 if discrete_2 is not None else False,
            discrete_3 if discrete_3 is not None else False,
            discrete_4 if discrete_4 is not None else False,
        ),
    )


def parse_gps_pvt(data: bytes) -> GpsPvt:
    """
    Parse GPS PVT message (escape '@').

    Expected length: 57 bytes (per G3X spec, includes CR/LF)
    This message has no checksum.
    """
    if len(data) != 57:
        raise ParseError(f"GPS PVT message wrong length: {len(data)} (expected 57)")

    if not data.endswith(b"\r\n"):
        raise ParseError("GPS PVT message does not end with CR/LF")

    # Parse timestamp (YYMMDDHHMMSS at offset 1)
    timestamp = parse_timestamp(data, 1, include_date=True)

    # Latitude: N/S + degrees(2) + minutes*1000(5) = 8 chars starting at offset 13
    lat_hemi = parse_char_field(data, 13)
    lat_deg = parse_int_field(data, 14, 2)
    lat_min = parse_int_field(data, 16, 5)

    if lat_hemi is not None and lat_deg is not None and lat_min is not None:
        latitude = lat_deg + (lat_min / 1000.0) / 60.0
        if lat_hemi == "S":
            latitude = -latitude
    else:
        latitude = None

    # Longitude: E/W + degrees(3) + minutes*1000(5) = 9 chars starting at offset 21
    lon_hemi = parse_char_field(data, 21)
    lon_deg = parse_int_field(data, 22, 3)
    lon_min = parse_int_field(data, 25, 5)

    if lon_hemi is not None and lon_deg is not None and lon_min is not None:
        longitude = lon_deg + (lon_min / 1000.0) / 60.0
        if lon_hemi == "W":
            longitude = -longitude
    else:
        longitude = None

    # Position status: offset 30
    position_status = parse_char_field(data, 30)

    # Horizontal error: offset 31, width 3, meters
    horizontal_error = parse_int_field(data, 31, 3)

    # Altitude: offset 34, width 6, meters MSL, signed
    altitude_msl = parse_signed_int_field(data, 34, 6)

    # East/west velocity: direction(1) + magnitude(4, 0.1 m/s)
    ew_dir = parse_char_field(data, 40)
    ew_mag = parse_int_field(data, 41, 4)
    if ew_dir is not None and ew_mag is not None:
        velocity_east = ew_mag * 0.1
        if ew_dir == "W":
            velocity_east = -velocity_east
    else:
        velocity_east = None

    # North/south velocity: direction(1) + magnitude(4, 0.1 m/s)
    ns_dir = parse_char_field(data, 45)
    ns_mag = parse_int_field(data, 46, 4)
    if ns_dir is not None and ns_mag is not None:
        velocity_north = ns_mag * 0.1
        if ns_dir == "S":
            velocity_north = -velocity_north
    else:
        velocity_north = None

    # Vertical velocity: direction(1) + magnitude(4, 0.01 m/s)
    vert_dir = parse_char_field(data, 50)
    vert_mag = parse_int_field(data, 51, 4)
    if vert_dir is not None and vert_mag is not None:
        velocity_vertical = vert_mag * 0.01
        if vert_dir == "D":
            velocity_vertical = -velocity_vertical
    else:
        velocity_vertical = None

    return GpsPvt(
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        position_status=position_status,
        horizontal_error=horizontal_error,
        altitude_msl=altitude_msl,
        velocity_east=velocity_east,
        velocity_north=velocity_north,
        velocity_vertical=velocity_vertical,
    )


def parse_gps_data(data: bytes) -> GpsData:
    """
    Parse GPS Data message (ID '7').

    Expected length: 22 bytes
    """
    if len(data) != 22:
        raise ParseError(f"GPS Data message wrong length: {len(data)} (expected 22)")

    verify_checksum(data)

    timestamp = parse_timestamp(data, 3)

    # Height AGL: offset 11, width 3, 100 ft
    height_raw = parse_int_field(data, 11, 3)
    height_agl = height_raw * 100 if height_raw is not None else None

    # Ground speed: offset 14, width 4, 0.1 knots
    ground_speed = parse_scaled_field(data, 14, 4, 0.1, signed=False)

    return GpsData(
        timestamp=timestamp,
        height_agl=height_agl,
        ground_speed=ground_speed,
    )


def parse_eis_parameter_info(data: bytes) -> list[EisParameterInfo]:
    """
    Parse EIS Parameter Information message (ID '5i').

    Variable length message with 19-byte records after the header.
    """
    verify_checksum(data)

    # Header: = + '5' + '1' + 'i' = 4 bytes
    # Each record: param_id(2 hex) + units(1) + name(16) = 19 bytes
    # Footer: checksum(2) + CR + LF = 4 bytes

    header_len = 4
    footer_len = 4
    record_len = 19

    payload_len = len(data) - header_len - footer_len
    if payload_len < 0 or payload_len % record_len != 0:
        raise ParseError(f"EIS Parameter Info message invalid length: {len(data)}")

    num_records = payload_len // record_len
    parameters = []

    for i in range(num_records):
        offset = header_len + i * record_len

        # Parameter ID: 2 hex chars
        param_id_hex = data[offset : offset + 2]
        try:
            param_id = int(param_id_hex, 16)
        except ValueError as e:
            raise ParseError(f"Invalid parameter ID hex: {param_id_hex!r}") from e

        # Units: 1 char
        units = chr(data[offset + 2])

        # Name: 16 chars (null-terminated if shorter)
        name = data[offset + 3 : offset + 19].decode("ascii").rstrip("\x00 ")

        parameters.append(EisParameterInfo(parameter_id=param_id, units=units, name=name))

    return parameters


def parse_eis_discrete_data(data: bytes) -> EisDiscreteData:
    """
    Parse EIS Discrete Parameter Data message (ID '5D').

    Variable length message with 3-byte records after the header.
    """
    verify_checksum(data)

    # Header: = + '5' + '1' + 'D' + timestamp(8) = 12 bytes
    # Each record: param_id(2 hex) + value(1) = 3 bytes
    # Footer: checksum(2) + CR + LF = 4 bytes

    header_len = 12
    footer_len = 4
    record_len = 3

    timestamp = parse_timestamp(data, 4)

    payload_len = len(data) - header_len - footer_len
    if payload_len < 0 or payload_len % record_len != 0:
        raise ParseError(f"EIS Discrete Data message invalid length: {len(data)}")

    num_records = payload_len // record_len
    parameters: dict[int, bool] = {}

    for i in range(num_records):
        offset = header_len + i * record_len

        # Parameter ID: 2 hex chars
        param_id_hex = data[offset : offset + 2]
        try:
            param_id = int(param_id_hex, 16)
        except ValueError as e:
            raise ParseError(f"Invalid parameter ID hex: {param_id_hex!r}") from e

        # Value: '1' or '0'
        value_char = chr(data[offset + 2])
        if value_char == "1":
            parameters[param_id] = True
        elif value_char == "0":
            parameters[param_id] = False
        else:
            raise ParseError(f"Invalid discrete value: {value_char!r}")

    return EisDiscreteData(timestamp=timestamp, parameters=parameters)


def parse_eis_numeric_data(data: bytes, engine: int) -> EisNumericData:
    """
    Parse EIS Numeric Parameter Data message (ID '51' or '52').

    Variable length message with 13-byte records after the header.

    Args:
        data: Raw message bytes
        engine: Engine number (1 or 2)
    """
    verify_checksum(data)

    # Header: = + '5' + '1' + engine + timestamp(8) = 12 bytes
    # Each record: param_id(2 hex) + value(11 scientific) = 13 bytes
    # Footer: checksum(2) + CR + LF = 4 bytes

    header_len = 12
    footer_len = 4
    record_len = 13

    timestamp = parse_timestamp(data, 4)

    payload_len = len(data) - header_len - footer_len
    if payload_len < 0 or payload_len % record_len != 0:
        raise ParseError(f"EIS Numeric Data message invalid length: {len(data)}")

    num_records = payload_len // record_len
    parameters: dict[int, Optional[float]] = {}

    for i in range(num_records):
        offset = header_len + i * record_len

        # Parameter ID: 2 hex chars
        param_id_hex = data[offset : offset + 2]
        try:
            param_id = int(param_id_hex, 16)
        except ValueError as e:
            raise ParseError(f"Invalid parameter ID hex: {param_id_hex!r}") from e

        # Value: 11 chars in scientific notation
        value_str = data[offset + 2 : offset + 13].decode("ascii")
        value = parse_scientific_notation(value_str)
        parameters[param_id] = value

    return EisNumericData(timestamp=timestamp, engine=engine, parameters=parameters)


def parse_cni_data(data: bytes) -> CniData:
    """
    Parse CNI message (ID 'C').

    Expected length: 131 bytes
    """
    if len(data) != 131:
        raise ParseError(f"CNI message wrong length: {len(data)} (expected 131)")

    verify_checksum(data)

    timestamp = parse_timestamp(data, 3)

    # COM1
    com1_active_freq = parse_int_field(data, 11, 6)
    com1_standby_freq = parse_int_field(data, 17, 6)
    com1_status = parse_char_field(data, 23)
    com1_monitor_enabled = parse_bool_field(data, 24)
    com1_fail = parse_bool_field(data, 25)
    com1_squelch_bypass = parse_bool_field(data, 26)
    com1_volume = parse_int_field(data, 27, 3)

    # COM2
    com2_active_freq = parse_int_field(data, 30, 6)
    com2_standby_freq = parse_int_field(data, 36, 6)
    com2_status = parse_char_field(data, 42)
    com2_monitor_enabled = parse_bool_field(data, 43)
    com2_fail = parse_bool_field(data, 44)
    com2_squelch_bypass = parse_bool_field(data, 45)
    com2_volume = parse_int_field(data, 46, 3)

    # Navigation source
    nav_source = parse_char_field(data, 49)

    # NAV1
    nav1_active_freq = parse_int_field(data, 50, 6)
    nav1_standby_freq = parse_int_field(data, 56, 6)
    nav1_ident = parse_string_field(data, 62, 10)
    nav1_fail = parse_bool_field(data, 72)
    nav1_volume = parse_int_field(data, 73, 3)

    # NAV2
    nav2_active_freq = parse_int_field(data, 76, 6)
    nav2_standby_freq = parse_int_field(data, 82, 6)
    nav2_ident = parse_string_field(data, 88, 10)
    nav2_fail = parse_bool_field(data, 98)
    nav2_volume = parse_int_field(data, 99, 3)

    # Audio panel
    audio_com1_rx = parse_bool_field(data, 102)
    audio_com2_rx = parse_bool_field(data, 103)
    audio_com1_tx = parse_bool_field(data, 104)
    audio_com2_tx = parse_bool_field(data, 105)
    audio_nav1_rx = parse_bool_field(data, 106)
    audio_nav2_rx = parse_bool_field(data, 107)
    audio_intercom_isolate = parse_char_field(data, 108)
    audio_marker_beacon = parse_char_field(data, 109)
    audio_panel_fail = parse_bool_field(data, 110)

    # Transponder
    transponder_mode = parse_char_field(data, 111)
    transponder_code = parse_int_field(data, 112, 4)
    transponder_ident = parse_bool_field(data, 116)
    transponder_reply = parse_bool_field(data, 117)
    transponder_flight_id = parse_string_field(data, 118, 8)
    transponder_fail = parse_bool_field(data, 126)

    return CniData(
        timestamp=timestamp,
        com1_active_freq=com1_active_freq,
        com1_standby_freq=com1_standby_freq,
        com1_status=com1_status,
        com1_monitor_enabled=com1_monitor_enabled,
        com1_fail=com1_fail,
        com1_squelch_bypass=com1_squelch_bypass,
        com1_volume=com1_volume,
        com2_active_freq=com2_active_freq,
        com2_standby_freq=com2_standby_freq,
        com2_status=com2_status,
        com2_monitor_enabled=com2_monitor_enabled,
        com2_fail=com2_fail,
        com2_squelch_bypass=com2_squelch_bypass,
        com2_volume=com2_volume,
        nav_source=nav_source,
        nav1_active_freq=nav1_active_freq,
        nav1_standby_freq=nav1_standby_freq,
        nav1_ident=nav1_ident,
        nav1_fail=nav1_fail,
        nav1_volume=nav1_volume,
        nav2_active_freq=nav2_active_freq,
        nav2_standby_freq=nav2_standby_freq,
        nav2_ident=nav2_ident,
        nav2_fail=nav2_fail,
        nav2_volume=nav2_volume,
        audio_com1_rx=audio_com1_rx,
        audio_com2_rx=audio_com2_rx,
        audio_com1_tx=audio_com1_tx,
        audio_com2_tx=audio_com2_tx,
        audio_nav1_rx=audio_nav1_rx,
        audio_nav2_rx=audio_nav2_rx,
        audio_intercom_isolate=audio_intercom_isolate,
        audio_marker_beacon=audio_marker_beacon,
        audio_panel_fail=audio_panel_fail,
        transponder_mode=transponder_mode,
        transponder_code=transponder_code,
        transponder_ident=transponder_ident,
        transponder_reply=transponder_reply,
        transponder_flight_id=transponder_flight_id,
        transponder_fail=transponder_fail,
    )


# =============================================================================
# Reader Class
# =============================================================================


class G3XTextReader:
    """Parser for G3X Text Out serial data."""

    def __init__(self, handler: G3XTextHandler) -> None:
        """Initialize reader with a message handler."""
        self._handler = handler
        self._eis_parameters: dict[int, EisParameterInfo] = {}
        self._serial_port = None

    def get_eis_parameters(self) -> dict[int, EisParameterInfo]:
        """Return current EIS parameter definitions."""
        return dict(self._eis_parameters)

    def clear_eis_parameters(self) -> None:
        """Clear cached EIS parameter definitions."""
        self._eis_parameters.clear()

    def parse_message(self, data: bytes) -> G3XMessage:
        """
        Parse a single message and return the appropriate dataclass.

        Args:
            data: Complete message bytes including CR/LF

        Returns:
            Parsed message dataclass

        Raises:
            ChecksumError: If checksum validation fails
            ParseError: If message format is invalid
        """
        msg_type, _version = identify_message_type(data)

        if msg_type == "@":
            return parse_gps_pvt(data)
        elif msg_type == "1":
            return parse_attitude_air_data(data)
        elif msg_type == "2":
            return parse_attitude_air_data_set2(data)
        elif msg_type == "3":
            return parse_engine_data(data)
        elif msg_type == "7":
            return parse_gps_data(data)
        elif msg_type == "C":
            return parse_cni_data(data)
        elif msg_type == "5i":
            params = parse_eis_parameter_info(data)
            # Cache the parameters
            for param in params:
                self._eis_parameters[param.parameter_id] = param
            return params[0] if len(params) == 1 else params  # type: ignore
        elif msg_type == "5D":
            return parse_eis_discrete_data(data)
        elif msg_type in ("51", "52"):
            engine = int(msg_type[1])
            return parse_eis_numeric_data(data, engine)
        else:
            raise ParseError(f"Unknown message type: {msg_type}")

    def _dispatch_message(self, message: G3XMessage) -> None:
        """Dispatch parsed message to appropriate handler method."""
        if isinstance(message, AttitudeAirData):
            self._handler.on_attitude_air_data(message)
        elif isinstance(message, AttitudeAirDataSet2):
            self._handler.on_attitude_air_data_set2(message)
        elif isinstance(message, EngineData):
            self._handler.on_engine_data(message)
        elif isinstance(message, GpsPvt):
            self._handler.on_gps_pvt(message)
        elif isinstance(message, GpsData):
            self._handler.on_gps_data(message)
        elif isinstance(message, list) and message and isinstance(message[0], EisParameterInfo):
            self._handler.on_eis_parameter_info(message)
        elif isinstance(message, EisParameterInfo):
            self._handler.on_eis_parameter_info([message])
        elif isinstance(message, EisDiscreteData):
            self._handler.on_eis_discrete_data(message)
        elif isinstance(message, EisNumericData):
            self._handler.on_eis_numeric_data(message)
        elif isinstance(message, CniData):
            self._handler.on_cni_data(message)

    def open_serial(self, port: str) -> None:
        """
        Open serial port with G3X Text Out settings (115200 8N1).

        Args:
            port: Serial port name (e.g., '/dev/ttyUSB0' or 'COM3')

        Raises:
            ImportError: If pyserial is not installed
        """
        try:
            import serial
        except ImportError as e:
            raise ImportError("pyserial is required for serial port support. Install with: pip install pyserial") from e

        self._serial_port = serial.Serial(
            port=port,
            baudrate=BAUD_RATE,
            bytesize=DATA_BITS,
            stopbits=STOP_BITS,
            parity=PARITY,
            timeout=1.0,
        )

    def close(self) -> None:
        """Close serial port."""
        if self._serial_port is not None:
            self._serial_port.close()
            self._serial_port = None

    def _process_line(self, line: bytes, context: str = "") -> bool:
        """
        Parse and dispatch a single message line.

        Args:
            line: Complete message bytes including CR/LF
            context: Optional context for error messages (e.g., "Line 123: ")

        Returns:
            True if successful, False if parse error occurred
        """
        try:
            message = self.parse_message(line)
            self._dispatch_message(message)
            return True
        except G3XTextError as e:
            print(f"Warning: {context}{e}", file=sys.stderr)
            return False

    def read_loop(self) -> int:
        """
        Read and process messages until interrupted, port closed, or serial error.

        Returns:
            Number of parse errors encountered

        Raises:
            RuntimeError: If serial port is not open
        """
        if self._serial_port is None:
            raise RuntimeError("Serial port not open")

        # Import serial here to access exception types
        import serial

        buffer = b""
        error_count = 0

        while True:
            try:
                chunk = self._serial_port.read(256)
                if not chunk:
                    continue

                buffer += chunk

                # Process complete messages
                while b"\r\n" in buffer:
                    idx = buffer.index(b"\r\n") + 2
                    line = buffer[:idx]
                    buffer = buffer[idx:]

                    if not self._process_line(line):
                        error_count += 1

            except KeyboardInterrupt:
                break
            except serial.SerialException as e:
                # Device disconnected, port error, etc.
                print(f"Serial error: {e}", file=sys.stderr)
                break

        return error_count

    def read_file(self, path: Path) -> int:
        """
        Read and process messages from a file (one message per line).

        Args:
            path: Path to file containing G3X Text Out data

        Returns:
            Number of parse errors encountered
        """
        error_count = 0

        with open(path, "rb") as f:
            for line_num, line in enumerate(f, 1):
                # Ensure line ends with CR/LF
                if not line.endswith(b"\r\n"):
                    line = line[:-1] + b"\r\n" if line.endswith(b"\n") else line + b"\r\n"

                if not self._process_line(line, f"Line {line_num}: "):
                    error_count += 1

        return error_count


# =============================================================================
# CLI Handler
# =============================================================================


class PrintHandler:
    """Simple handler that prints parsed messages."""

    def __init__(self, verbose: bool = False, filters: Optional[list[str]] = None):
        self.verbose = verbose
        self.filters = set(filters) if filters else None
        self.message_counts: dict[str, int] = {}

    def _should_print(self, msg_type: str) -> bool:
        if self.filters is None:
            return True
        return msg_type in self.filters

    def _count(self, msg_type: str) -> None:
        self.message_counts[msg_type] = self.message_counts.get(msg_type, 0) + 1

    def on_attitude_air_data(self, data: AttitudeAirData) -> None:
        self._count("attitude")
        if self._should_print("attitude") and self.verbose:
            print(
                f"[ATTITUDE] pitch={data.pitch}° roll={data.roll}° hdg={data.heading}° "
                f"ias={data.airspeed}kt alt={data.pressure_altitude}ft"
            )

    def on_attitude_air_data_set2(self, data: AttitudeAirDataSet2) -> None:
        self._count("attitude2")
        if self._should_print("attitude2") and self.verbose:
            print(
                f"[ATTITUDE2] tas={data.true_airspeed}kt da={data.density_altitude}ft "
                f"hdg_bug={data.heading_bug}° alt_bug={data.altitude_bug}ft"
            )

    def on_engine_data(self, data: EngineData) -> None:
        self._count("engine")
        if self._should_print("engine") and self.verbose:
            print(
                f"[ENGINE] rpm={data.rpm} oil_p={data.oil_pressure}psi "
                f"oil_t={data.oil_temperature}°C ff={data.fuel_flow}gph"
            )

    def on_gps_pvt(self, data: GpsPvt) -> None:
        self._count("gps")
        if self._should_print("gps") and self.verbose:
            print(
                f"[GPS_PVT] lat={data.latitude} lon={data.longitude} "
                f"alt={data.altitude_msl}m status={data.position_status}"
            )

    def on_gps_data(self, data: GpsData) -> None:
        self._count("gps")
        if self._should_print("gps") and self.verbose:
            print(f"[GPS] agl={data.height_agl}ft gs={data.ground_speed}kt")

    def on_eis_parameter_info(self, data: list[EisParameterInfo]) -> None:
        self._count("eis")
        if self._should_print("eis") and self.verbose:
            for param in data:
                print(f"[EIS_INFO] id=0x{param.parameter_id:02X} units={param.units} name={param.name}")

    def on_eis_discrete_data(self, data: EisDiscreteData) -> None:
        self._count("eis")
        if self._should_print("eis") and self.verbose:
            active = [f"0x{pid:02X}" for pid, val in data.parameters.items() if val]
            print(f"[EIS_DISCRETE] active={active}")

    def on_eis_numeric_data(self, data: EisNumericData) -> None:
        self._count("eis")
        if self._should_print("eis") and self.verbose:
            params = [f"0x{pid:02X}={val}" for pid, val in data.parameters.items()]
            print(f"[EIS_NUMERIC] engine={data.engine} {' '.join(params[:5])}...")

    def on_cni_data(self, data: CniData) -> None:
        self._count("cni")
        if self._should_print("cni") and self.verbose:
            print(
                f"[CNI] com1={data.com1_active_freq}kHz nav1={data.nav1_active_freq}kHz "
                f"xpdr={data.transponder_code} mode={data.transponder_mode}"
            )


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Parse G3X Text Out RS-232 data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  g3xtext /dev/ttyUSB0              Read from serial port
  g3xtext --file g3x_flight.log     Read from file
  g3xtext -v /dev/ttyUSB0           Verbose output
  g3xtext --filter attitude,gps /dev/ttyUSB0

Filter values:
  attitude  - Attitude/Air Data (ID 1)
  attitude2 - Attitude/Air Data Set 2 (ID 2)
  engine    - Engine Data (ID 3)
  eis       - EIS messages (ID 5*)
  gps       - GPS PVT (@) and GPS Data (ID 7)
  cni       - CNI message (ID C)
""",
    )

    parser.add_argument("port", nargs="?", help="Serial port (e.g., /dev/ttyUSB0 or COM3)")
    parser.add_argument("-f", "--file", type=Path, help="Read from file instead of serial port")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--filter",
        type=str,
        help="Comma-separated list of message types to display",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.file is None and args.port is None:
        parser.error("Either PORT or --file must be specified")

    if args.file is not None and args.port is not None:
        parser.error("Cannot specify both PORT and --file")

    # Parse filters
    filters = None
    if args.filter:
        filters = [f.strip().lower() for f in args.filter.split(",")]
        valid_filters = {"attitude", "attitude2", "engine", "eis", "gps", "cni"}
        invalid = set(filters) - valid_filters
        if invalid:
            parser.error(f"Invalid filter(s): {invalid}. Valid: {valid_filters}")

    # Create handler and reader
    handler = PrintHandler(verbose=args.verbose, filters=filters)
    reader = G3XTextReader(handler)

    try:
        if args.file:
            if not args.file.exists():
                print(f"Error: File not found: {args.file}", file=sys.stderr)
                return 1

            error_count = reader.read_file(args.file)

            # Print summary
            total_messages = sum(handler.message_counts.values())
            if handler.message_counts:
                print(f"\nProcessed {total_messages} messages:")
                for msg_type, count in sorted(handler.message_counts.items()):
                    print(f"  {msg_type}: {count}")
            if error_count > 0:
                print(f"  Errors: {error_count}")
        else:
            try:
                reader.open_serial(args.port)
            except ImportError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"Error opening serial port: {e}", file=sys.stderr)
                return 1

            print(f"Reading from {args.port} (115200 8N1)... Press Ctrl+C to stop.")
            try:
                error_count = reader.read_loop()
            finally:
                reader.close()

            # Print summary
            total_messages = sum(handler.message_counts.values())
            if handler.message_counts:
                print(f"\nProcessed {total_messages} messages:")
                for msg_type, count in sorted(handler.message_counts.items()):
                    print(f"  {msg_type}: {count}")
            if error_count > 0:
                print(f"  Errors: {error_count}")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
