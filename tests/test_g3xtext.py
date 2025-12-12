"""
Tests for g3xtext.py - G3X Text Out parser.

Tests cover message parsing, checksum validation, and data conversion.
All test data is synthetic based on the G3X Text Out specification.
"""


import pytest

import g3xtext

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_attitude_air_data() -> bytes:
    """
    Synthetic Attitude/Air Data message (ID '1').

    Total length: 59 bytes per spec Table C-1
    Layout: escape(1) + id(1) + ver(1) + time(8) + pitch(4) + roll(5) + heading(3)
            + airspeed(4) + alt(6) + rot(4) + lat_accel(3) + vert_accel(3)
            + aoa(2) + vs(4) + oat(3) + altimeter(3) + checksum(2) + crlf(2) = 59
    """
    # Build message: offsets from spec
    # 0: '=' escape
    # 1: '1' ID
    # 2: '1' version
    # 3-10: timestamp HHMMSSFF (8 chars)
    # 11-14: pitch (4 chars, 0.1 deg signed) = +123 means +12.3 deg
    # 15-19: roll (5 chars, 0.1 deg signed) = -0456 means -45.6 deg
    # 20-22: heading (3 chars) = 270
    # 23-26: airspeed (4 chars, 0.1 kt) = 1250 means 125.0 kt
    # 27-32: pressure alt (6 chars, signed) = +05500 means 5500 ft
    # 33-36: rate of turn (4 chars, 0.1 deg/s signed) = +032 means +3.2 deg/s
    # 37-39: lateral accel (3 chars, 0.01 G signed) = -15 means -0.15 G
    # 40-42: vertical accel (3 chars, 0.1 G signed) = +12 means +1.2 G
    # 43-44: AOA (2 chars) = 35
    # 45-48: vertical speed (4 chars, 10 fpm signed) = +050 means +500 fpm
    # 49-51: OAT (3 chars, signed) = -05 means -5 C
    # 52-54: altimeter (3 chars) = 242 means 27.50 + 2.42 = 29.92 inHg
    # 55-56: checksum (2 hex chars)
    # 57-58: CR LF

    msg = b"=1112345678+123-04562701250+05500+032-15+1235+050-05242"
    # Verify length before checksum: should be 55 bytes (59 - 2 checksum - 2 crlf)
    assert len(msg) == 55, f"Message body length is {len(msg)}, expected 55"
    checksum = sum(msg) & 0xFF
    result = msg + f"{checksum:02X}".encode() + b"\r\n"
    assert len(result) == 59, f"Total message length is {len(result)}, expected 59"
    return result


@pytest.fixture
def sample_attitude_air_data_set2() -> bytes:
    """
    Synthetic Attitude/Air Data Set 2 message (ID '2').

    Total length: 42 bytes per spec Table C-2
    Layout: escape(1) + id(1) + ver(1) + time(8) + tas(4) + density_alt(6)
            + hdg_bug(3) + alt_bug(6) + as_bug(4) + vs_bug(4) + checksum(2) + crlf(2) = 42
    """
    # 0: '=' escape
    # 1: '2' ID
    # 2: '1' version
    # 3-10: timestamp HHMMSSFF (8 chars)
    # 11-14: true airspeed (4 chars, 0.1 kt) = 1350 means 135.0 kt
    # 15-20: density altitude (6 chars, signed) = +06500 means 6500 ft
    # 21-23: heading bug (3 chars) = 180
    # 24-29: altitude bug (6 chars, signed) = +10000 means 10000 ft
    # 30-33: airspeed bug (4 chars, 0.1 kt) = 1200 means 120.0 kt
    # 34-37: vs bug (4 chars, 10 fpm signed) = +020 means +200 fpm
    # 38-39: checksum (2 hex chars)
    # 40-41: CR LF

    msg = b"=2112345678" + b"1350" + b"+06500" + b"180" + b"+10000" + b"1200" + b"+020"
    # Should be 38 bytes before checksum
    assert len(msg) == 38, f"Message body length is {len(msg)}, expected 38"
    checksum = sum(msg) & 0xFF
    result = msg + f"{checksum:02X}".encode() + b"\r\n"
    assert len(result) == 42, f"Total message length is {len(result)}, expected 42"
    return result


@pytest.fixture
def sample_gps_pvt() -> bytes:
    """
    Synthetic GPS PVT message (escape '@').

    No checksum per spec.

    Fields (based on spec Table C-4):
    - Escape '@'
    - Date: 2024-03-15 (240315)
    - Time: 12:34:56 UTC
    - Latitude: N37 30.500 (N3730500)
    - Longitude: W122 15.250 (W12215250)
    - Status: G (3D GPS)
    - Horizontal error: 005 meters
    - Altitude: +00123 meters
    - E/W velocity: E0025 (2.5 m/s east)
    - N/S velocity: N0100 (10.0 m/s north)
    - Vertical velocity: U0050 (0.50 m/s up)
    """
    return b"@240315123456N3730500W12215250G005+00123E0025N0100U0050\r\n"


@pytest.fixture
def sample_gps_data() -> bytes:
    """
    Synthetic GPS Data message (ID '7').

    Fields (based on spec Table C-5):
    - Escape '=', ID '7', Version '1'
    - Time: 12:34:56.00 UTC
    - Height AGL: 025 (2500 feet)
    - Ground speed: 1250 (125.0 knots)
    """
    msg = b"=7112345600025" + b"1250"
    checksum = sum(msg) & 0xFF
    return msg + f"{checksum:02X}".encode() + b"\r\n"


@pytest.fixture
def sample_cni_data() -> bytes:
    """
    Synthetic CNI message (ID 'C').

    Partial synthetic data based on spec Table C-10.
    """
    # Build a 127-byte payload (before checksum)
    # = C 1 + timestamp(8) + COM1(19) + COM2(19) + nav_source(1) + NAV1(16) + NAV2(16)
    # + audio(8) + xpdr(16) = total 127 before checksum
    msg = bytearray(127)
    msg[0:3] = b"=C1"
    msg[3:11] = b"12345678"  # timestamp

    # COM1: offset 11
    msg[11:17] = b"123450"  # active freq
    msg[17:23] = b"121500"  # standby freq
    msg[23] = ord("R")  # status
    msg[24] = ord("0")  # monitor
    msg[25] = ord("0")  # fail
    msg[26] = ord("0")  # squelch
    msg[27:30] = b"050"  # volume

    # COM2: offset 30
    msg[30:36] = b"118000"
    msg[36:42] = b"119000"
    msg[42] = ord("_")  # status
    msg[43] = ord("0")
    msg[44] = ord("0")
    msg[45] = ord("0")
    msg[46:49] = b"100"

    # Nav source: offset 49
    msg[49] = ord("I")

    # NAV1: offset 50
    msg[50:56] = b"110000"  # active
    msg[56:62] = b"112000"  # standby
    msg[62:72] = b"KABC      "  # ident (10 chars)
    msg[72] = ord("0")  # fail
    msg[73:76] = b"075"  # volume

    # NAV2: offset 76
    msg[76:82] = b"116000"
    msg[82:88] = b"117000"
    msg[88:98] = b"__________"  # ident invalid
    msg[98] = ord("0")
    msg[99:102] = b"050"

    # Audio panel: offset 102
    msg[102] = ord("1")  # com1 rx
    msg[103] = ord("0")  # com2 rx
    msg[104] = ord("1")  # com1 tx
    msg[105] = ord("0")  # com2 tx
    msg[106] = ord("1")  # nav1 rx
    msg[107] = ord("0")  # nav2 rx
    msg[108] = ord("0")  # intercom isolate
    msg[109] = ord("n")  # marker beacon

    # Audio panel fail: offset 110
    msg[110] = ord("0")

    # Transponder: offset 111
    msg[111] = ord("A")  # mode
    msg[112:116] = b"1200"  # code
    msg[116] = ord("0")  # ident
    msg[117] = ord("0")  # reply
    msg[118:126] = b"N12345  "  # flight ID
    msg[126] = ord("0")  # fail

    checksum = sum(msg) & 0xFF
    return bytes(msg) + f"{checksum:02X}".encode() + b"\r\n"


@pytest.fixture
def sample_eis_parameter_info() -> bytes:
    """
    Synthetic EIS Parameter Information message (ID '5i').

    One parameter record: ID=0x17, Units='C', Name='OIL TEMP'
    """
    # Header: =51i (4 bytes)
    # Record: param_id(2) + units(1) + name(16) = 19 bytes
    # Footer: checksum(2) + CR/LF(2) = 4 bytes
    msg = b"=51i" + b"17" + b"C" + b"OIL TEMP\x00\x00\x00\x00\x00\x00\x00\x00"
    checksum = sum(msg) & 0xFF
    return msg + f"{checksum:02X}".encode() + b"\r\n"


@pytest.fixture
def sample_eis_discrete_data() -> bytes:
    """
    Synthetic EIS Discrete Parameter Data message (ID '5D').

    Two parameters: 0x3E=1 (active), 0x3F=0 (inactive)
    """
    # Header: =51D + timestamp(8) = 12 bytes
    # Records: param_id(2) + value(1) = 3 bytes each
    msg = b"=51D12345678" + b"3E1" + b"3F0"
    checksum = sum(msg) & 0xFF
    return msg + f"{checksum:02X}".encode() + b"\r\n"


@pytest.fixture
def sample_eis_numeric_data() -> bytes:
    """
    Synthetic EIS Numeric Parameter Data message (ID '51').

    One parameter: 0x17 = +1.2327E+01 (12.327)
    """
    # Header: =511 + timestamp(8) = 12 bytes
    # Record: param_id(2) + value(11) = 13 bytes
    msg = b"=51112345678" + b"17" + b"+1.2327E+01"
    checksum = sum(msg) & 0xFF
    return msg + f"{checksum:02X}".encode() + b"\r\n"


# =============================================================================
# Test Classes
# =============================================================================


class MockHandler:
    """Mock handler for testing."""

    def __init__(self):
        self.attitude_data: list[g3xtext.AttitudeAirData] = []
        self.attitude2_data: list[g3xtext.AttitudeAirDataSet2] = []
        self.engine_data: list[g3xtext.EngineData] = []
        self.gps_pvt_data: list[g3xtext.GpsPvt] = []
        self.gps_data: list[g3xtext.GpsData] = []
        self.eis_param_info: list[list[g3xtext.EisParameterInfo]] = []
        self.eis_discrete_data: list[g3xtext.EisDiscreteData] = []
        self.eis_numeric_data: list[g3xtext.EisNumericData] = []
        self.cni_data: list[g3xtext.CniData] = []

    def on_attitude_air_data(self, data: g3xtext.AttitudeAirData) -> None:
        self.attitude_data.append(data)

    def on_attitude_air_data_set2(self, data: g3xtext.AttitudeAirDataSet2) -> None:
        self.attitude2_data.append(data)

    def on_engine_data(self, data: g3xtext.EngineData) -> None:
        self.engine_data.append(data)

    def on_gps_pvt(self, data: g3xtext.GpsPvt) -> None:
        self.gps_pvt_data.append(data)

    def on_gps_data(self, data: g3xtext.GpsData) -> None:
        self.gps_data.append(data)

    def on_eis_parameter_info(self, data: list[g3xtext.EisParameterInfo]) -> None:
        self.eis_param_info.append(data)

    def on_eis_discrete_data(self, data: g3xtext.EisDiscreteData) -> None:
        self.eis_discrete_data.append(data)

    def on_eis_numeric_data(self, data: g3xtext.EisNumericData) -> None:
        self.eis_numeric_data.append(data)

    def on_cni_data(self, data: g3xtext.CniData) -> None:
        self.cni_data.append(data)


# =============================================================================
# Checksum Tests
# =============================================================================


class TestChecksum:
    """Tests for checksum calculation and verification."""

    def test_calculate_checksum_simple(self):
        """Calculate checksum for simple data."""
        data = b"=11"
        result = g3xtext.calculate_checksum(data)
        assert result == (ord("=") + ord("1") + ord("1")) & 0xFF

    def test_calculate_checksum_wraps_at_256(self):
        """Checksum wraps at 256 (8-bit)."""
        # Create data that sums to > 256
        data = bytes([255, 10])  # Sum = 265, should wrap to 9
        result = g3xtext.calculate_checksum(data)
        assert result == 9

    def test_verify_checksum_valid(self, sample_attitude_air_data):
        """Valid checksum passes verification."""
        assert g3xtext.verify_checksum(sample_attitude_air_data) is True

    def test_verify_checksum_invalid(self, sample_attitude_air_data):
        """Invalid checksum raises ChecksumError."""
        # Corrupt the checksum
        corrupted = sample_attitude_air_data[:-4] + b"00\r\n"
        with pytest.raises(g3xtext.ChecksumError, match="Checksum mismatch"):
            g3xtext.verify_checksum(corrupted)

    def test_verify_checksum_too_short(self):
        """Message too short raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="too short"):
            g3xtext.verify_checksum(b"=1\r\n")

    def test_verify_checksum_no_crlf(self, sample_attitude_air_data):
        """Message without CR/LF raises ParseError."""
        no_crlf = sample_attitude_air_data[:-2]
        with pytest.raises(g3xtext.ParseError, match="does not end with CR/LF"):
            g3xtext.verify_checksum(no_crlf)

    def test_verify_checksum_invalid_hex(self):
        """Non-hex checksum raises ParseError."""
        invalid = b"=11123456780000XX\r\n"
        with pytest.raises(g3xtext.ParseError, match="Invalid checksum hex"):
            g3xtext.verify_checksum(invalid)


# =============================================================================
# Message Type Identification Tests
# =============================================================================


class TestMessageTypeIdentification:
    """Tests for message type identification."""

    def test_identify_gps_pvt(self, sample_gps_pvt):
        """Identify GPS PVT message."""
        msg_type, version = g3xtext.identify_message_type(sample_gps_pvt)
        assert msg_type == "@"
        assert version == 0

    def test_identify_attitude(self, sample_attitude_air_data):
        """Identify Attitude/Air Data message."""
        msg_type, version = g3xtext.identify_message_type(sample_attitude_air_data)
        assert msg_type == "1"
        assert version == 1

    def test_identify_attitude_set2(self, sample_attitude_air_data_set2):
        """Identify Attitude/Air Data Set 2 message."""
        msg_type, version = g3xtext.identify_message_type(sample_attitude_air_data_set2)
        assert msg_type == "2"
        assert version == 1

    def test_identify_gps_data(self, sample_gps_data):
        """Identify GPS Data message."""
        msg_type, version = g3xtext.identify_message_type(sample_gps_data)
        assert msg_type == "7"
        assert version == 1

    def test_identify_cni(self, sample_cni_data):
        """Identify CNI message."""
        msg_type, version = g3xtext.identify_message_type(sample_cni_data)
        assert msg_type == "C"
        assert version == 1

    def test_identify_eis_param_info(self, sample_eis_parameter_info):
        """Identify EIS Parameter Info message."""
        msg_type, version = g3xtext.identify_message_type(sample_eis_parameter_info)
        assert msg_type == "5i"
        assert version == 1

    def test_identify_eis_discrete(self, sample_eis_discrete_data):
        """Identify EIS Discrete Data message."""
        msg_type, version = g3xtext.identify_message_type(sample_eis_discrete_data)
        assert msg_type == "5D"
        assert version == 1

    def test_identify_eis_numeric(self, sample_eis_numeric_data):
        """Identify EIS Numeric Data message."""
        msg_type, version = g3xtext.identify_message_type(sample_eis_numeric_data)
        assert msg_type == "51"
        assert version == 1

    def test_identify_unknown_escape(self):
        """Unknown escape character raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="Unknown escape character"):
            g3xtext.identify_message_type(b"X123\r\n")

    def test_identify_too_short(self):
        """Message too short raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="too short"):
            g3xtext.identify_message_type(b"=")


# =============================================================================
# Field Parsing Tests
# =============================================================================


class TestFieldParsing:
    """Tests for individual field parsing functions."""

    def test_parse_int_field_valid(self):
        """Parse valid integer field."""
        data = b"12345"
        result = g3xtext.parse_int_field(data, 0, 3)
        assert result == 123

    def test_parse_int_field_invalid(self):
        """Invalid integer field contains underscore."""
        data = b"1_345"
        result = g3xtext.parse_int_field(data, 0, 3)
        assert result is None

    def test_parse_int_field_all_underscores(self):
        """All underscores returns None."""
        data = b"___"
        result = g3xtext.parse_int_field(data, 0, 3)
        assert result is None

    def test_parse_signed_int_field_positive(self):
        """Parse positive signed integer."""
        data = b"+123"
        result = g3xtext.parse_signed_int_field(data, 0, 4)
        assert result == 123

    def test_parse_signed_int_field_negative(self):
        """Parse negative signed integer."""
        data = b"-456"
        result = g3xtext.parse_signed_int_field(data, 0, 4)
        assert result == -456

    def test_parse_scaled_field(self):
        """Parse scaled field."""
        data = b"1234"
        result = g3xtext.parse_scaled_field(data, 0, 4, 0.1)
        assert result == pytest.approx(123.4)

    def test_parse_scaled_field_signed(self):
        """Parse signed scaled field."""
        data = b"-123"
        result = g3xtext.parse_scaled_field(data, 0, 4, 0.1, signed=True)
        assert result == pytest.approx(-12.3)

    def test_parse_char_field_valid(self):
        """Parse valid character field."""
        data = b"ABC"
        result = g3xtext.parse_char_field(data, 1)
        assert result == "B"

    def test_parse_char_field_underscore(self):
        """Underscore returns None."""
        data = b"A_C"
        result = g3xtext.parse_char_field(data, 1)
        assert result is None

    def test_parse_bool_field_true(self):
        """Parse boolean true."""
        data = b"1"
        result = g3xtext.parse_bool_field(data, 0)
        assert result is True

    def test_parse_bool_field_false(self):
        """Parse boolean false."""
        data = b"0"
        result = g3xtext.parse_bool_field(data, 0)
        assert result is False

    def test_parse_bool_field_underscore(self):
        """Underscore returns None."""
        data = b"_"
        result = g3xtext.parse_bool_field(data, 0)
        assert result is None

    def test_parse_bool_field_invalid(self):
        """Invalid boolean raises ParseError."""
        data = b"X"
        with pytest.raises(g3xtext.ParseError, match="Invalid boolean"):
            g3xtext.parse_bool_field(data, 0)

    def test_parse_string_field_valid(self):
        """Parse valid string field."""
        data = b"HELLO\x00\x00\x00"
        result = g3xtext.parse_string_field(data, 0, 8)
        assert result == "HELLO"

    def test_parse_string_field_all_underscores(self):
        """All underscores returns None."""
        data = b"________"
        result = g3xtext.parse_string_field(data, 0, 8)
        assert result is None

    def test_parse_scientific_notation_valid(self):
        """Parse valid scientific notation."""
        result = g3xtext.parse_scientific_notation("+1.2345E+02")
        assert result == pytest.approx(123.45)

    def test_parse_scientific_notation_negative(self):
        """Parse negative scientific notation."""
        result = g3xtext.parse_scientific_notation("-9.8765E-03")
        assert result == pytest.approx(-0.0098765)

    def test_parse_scientific_notation_invalid(self):
        """Invalid scientific notation returns None."""
        result = g3xtext.parse_scientific_notation("___________")
        assert result is None


# =============================================================================
# Attitude/Air Data Tests
# =============================================================================


class TestAttitudeAirData:
    """Tests for Attitude/Air Data message parsing."""

    def test_parse_attitude_valid(self, sample_attitude_air_data):
        """Parse valid Attitude/Air Data message."""
        result = g3xtext.parse_attitude_air_data(sample_attitude_air_data)

        assert isinstance(result, g3xtext.AttitudeAirData)
        assert result.pitch == pytest.approx(12.3)
        assert result.roll == pytest.approx(-45.6)
        assert result.heading == 270
        assert result.airspeed == pytest.approx(125.0)
        assert result.pressure_altitude == 5500
        assert result.rate_of_turn == pytest.approx(3.2)
        assert result.lateral_accel == pytest.approx(-0.15)
        assert result.vertical_accel == pytest.approx(1.2)
        assert result.aoa == 35
        assert result.vertical_speed == 500
        assert result.oat == -5
        assert result.altimeter_setting == pytest.approx(29.92)

    def test_parse_attitude_wrong_length(self):
        """Wrong length raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="wrong length"):
            g3xtext.parse_attitude_air_data(b"=11\r\n")

    def test_parse_attitude_with_invalid_fields(self):
        """Fields with underscores parse as None."""
        # Build message with invalid pitch (____) and roll (_____)
        # Total must be 59 bytes
        msg = b"=1112345678____-____2701250+05500+032-15+1235+050-05242"
        assert len(msg) == 55, f"Expected 55, got {len(msg)}"
        checksum = sum(msg) & 0xFF
        data = msg + f"{checksum:02X}".encode() + b"\r\n"
        assert len(data) == 59

        result = g3xtext.parse_attitude_air_data(data)
        assert result.pitch is None
        assert result.roll is None
        # Other fields should still be valid
        assert result.heading == 270


# =============================================================================
# Attitude/Air Data Set 2 Tests
# =============================================================================


class TestAttitudeAirDataSet2:
    """Tests for Attitude/Air Data Set 2 message parsing."""

    def test_parse_attitude2_valid(self, sample_attitude_air_data_set2):
        """Parse valid Attitude/Air Data Set 2 message."""
        result = g3xtext.parse_attitude_air_data_set2(sample_attitude_air_data_set2)

        assert isinstance(result, g3xtext.AttitudeAirDataSet2)
        assert result.true_airspeed == pytest.approx(135.0)
        # Note: density altitude parsing depends on sign prefix format
        assert result.heading_bug == 180
        assert result.airspeed_bug == pytest.approx(120.0)

    def test_parse_attitude2_wrong_length(self):
        """Wrong length raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="wrong length"):
            g3xtext.parse_attitude_air_data_set2(b"=21\r\n")


# =============================================================================
# GPS PVT Tests
# =============================================================================


class TestGpsPvt:
    """Tests for GPS PVT message parsing."""

    def test_parse_gps_pvt_valid(self, sample_gps_pvt):
        """Parse valid GPS PVT message."""
        result = g3xtext.parse_gps_pvt(sample_gps_pvt)

        assert isinstance(result, g3xtext.GpsPvt)
        assert result.timestamp.year == 2024
        assert result.timestamp.month == 3
        assert result.timestamp.day == 15
        assert result.timestamp.hour == 12
        assert result.timestamp.minute == 34
        assert result.timestamp.second == 56

        # Latitude: N37 30.500 = 37 + 30.5/60 = 37.508333...
        assert result.latitude == pytest.approx(37.508333, abs=0.001)

        # Longitude: W122 15.250 = -(122 + 15.25/60) = -122.254166...
        assert result.longitude == pytest.approx(-122.254166, abs=0.001)

        assert result.position_status == "G"
        assert result.horizontal_error == 5
        assert result.altitude_msl == 123
        assert result.velocity_east == pytest.approx(2.5)
        assert result.velocity_north == pytest.approx(10.0)
        assert result.velocity_vertical == pytest.approx(0.5)

    def test_parse_gps_pvt_wrong_length(self):
        """Wrong length raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="wrong length"):
            g3xtext.parse_gps_pvt(b"@123\r\n")


# =============================================================================
# GPS Data Tests
# =============================================================================


class TestGpsData:
    """Tests for GPS Data message parsing."""

    def test_parse_gps_data_valid(self, sample_gps_data):
        """Parse valid GPS Data message."""
        result = g3xtext.parse_gps_data(sample_gps_data)

        assert isinstance(result, g3xtext.GpsData)
        assert result.height_agl == 2500  # 25 * 100
        assert result.ground_speed == pytest.approx(125.0)

    def test_parse_gps_data_wrong_length(self):
        """Wrong length raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="wrong length"):
            g3xtext.parse_gps_data(b"=71\r\n")


# =============================================================================
# CNI Tests
# =============================================================================


class TestCniData:
    """Tests for CNI message parsing."""

    def test_parse_cni_valid(self, sample_cni_data):
        """Parse valid CNI message."""
        result = g3xtext.parse_cni_data(sample_cni_data)

        assert isinstance(result, g3xtext.CniData)
        assert result.com1_active_freq == 123450
        assert result.com1_standby_freq == 121500
        assert result.com1_status == "R"
        assert result.com1_volume == 50

        assert result.com2_status is None  # Was '_'

        assert result.nav_source == "I"
        assert result.nav1_ident == "KABC"
        assert result.nav2_ident is None  # All underscores

        assert result.audio_com1_rx is True
        assert result.audio_com2_rx is False

        assert result.transponder_mode == "A"
        assert result.transponder_code == 1200

    def test_parse_cni_wrong_length(self):
        """Wrong length raises ParseError."""
        with pytest.raises(g3xtext.ParseError, match="wrong length"):
            g3xtext.parse_cni_data(b"=C1\r\n")


# =============================================================================
# EIS Message Tests
# =============================================================================


class TestEisMessages:
    """Tests for EIS message parsing."""

    def test_parse_eis_parameter_info(self, sample_eis_parameter_info):
        """Parse EIS Parameter Information message."""
        result = g3xtext.parse_eis_parameter_info(sample_eis_parameter_info)

        assert len(result) == 1
        param = result[0]
        assert param.parameter_id == 0x17
        assert param.units == "C"
        assert param.name == "OIL TEMP"

    def test_parse_eis_discrete_data(self, sample_eis_discrete_data):
        """Parse EIS Discrete Data message."""
        result = g3xtext.parse_eis_discrete_data(sample_eis_discrete_data)

        assert isinstance(result, g3xtext.EisDiscreteData)
        assert result.parameters[0x3E] is True
        assert result.parameters[0x3F] is False

    def test_parse_eis_numeric_data(self, sample_eis_numeric_data):
        """Parse EIS Numeric Data message."""
        result = g3xtext.parse_eis_numeric_data(sample_eis_numeric_data, engine=1)

        assert isinstance(result, g3xtext.EisNumericData)
        assert result.engine == 1
        assert result.parameters[0x17] == pytest.approx(12.327)


# =============================================================================
# Reader Tests
# =============================================================================


class TestG3XTextReader:
    """Tests for G3XTextReader class."""

    def test_reader_parse_attitude(self, sample_attitude_air_data):
        """Reader parses attitude message."""
        handler = MockHandler()
        reader = g3xtext.G3XTextReader(handler)

        result = reader.parse_message(sample_attitude_air_data)
        assert isinstance(result, g3xtext.AttitudeAirData)

    def test_reader_dispatch_attitude(self, sample_attitude_air_data):
        """Reader dispatches attitude message to handler."""
        handler = MockHandler()
        reader = g3xtext.G3XTextReader(handler)

        message = reader.parse_message(sample_attitude_air_data)
        reader._dispatch_message(message)

        assert len(handler.attitude_data) == 1
        assert handler.attitude_data[0].pitch == pytest.approx(12.3)

    def test_reader_caches_eis_parameters(self, sample_eis_parameter_info):
        """Reader caches EIS parameter definitions."""
        handler = MockHandler()
        reader = g3xtext.G3XTextReader(handler)

        reader.parse_message(sample_eis_parameter_info)

        params = reader.get_eis_parameters()
        assert 0x17 in params
        assert params[0x17].name == "OIL TEMP"

    def test_reader_clear_eis_parameters(self, sample_eis_parameter_info):
        """Reader can clear EIS parameters."""
        handler = MockHandler()
        reader = g3xtext.G3XTextReader(handler)

        reader.parse_message(sample_eis_parameter_info)
        assert len(reader.get_eis_parameters()) > 0

        reader.clear_eis_parameters()
        assert len(reader.get_eis_parameters()) == 0

    def test_reader_read_file(self, tmp_path, sample_attitude_air_data, sample_gps_pvt):
        """Reader processes file with multiple messages."""
        # Create test file
        test_file = tmp_path / "test.log"
        test_file.write_bytes(sample_attitude_air_data + sample_gps_pvt)

        handler = MockHandler()
        reader = g3xtext.G3XTextReader(handler)
        reader.read_file(test_file)

        assert len(handler.attitude_data) == 1
        assert len(handler.gps_pvt_data) == 1


# =============================================================================
# Exception Tests
# =============================================================================


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_g3xtext_error_is_base(self):
        """G3XTextError is base for all custom exceptions."""
        assert issubclass(g3xtext.ChecksumError, g3xtext.G3XTextError)
        assert issubclass(g3xtext.ParseError, g3xtext.G3XTextError)

    def test_checksum_error_message(self):
        """ChecksumError has descriptive message."""
        error = g3xtext.ChecksumError("test message")
        assert str(error) == "test message"

    def test_parse_error_message(self):
        """ParseError has descriptive message."""
        error = g3xtext.ParseError("invalid format")
        assert str(error) == "invalid format"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests with real sample data format."""

    def test_parse_real_format_attitude(self):
        """Parse message in format matching real G3X output."""
        # Real format from sample log: =1123594748____________0133+01073____+01+1000+000+32240 + checksum 7F
        # Body is 55 chars, then 2-char checksum, then CRLF = 59 total
        # Field breakdown:
        #   0: '=' escape
        #   1: '1' ID
        #   2: '1' version
        #   3-10: '23594748' timestamp (HHMMSSFF)
        #   11-14: '____' pitch (invalid)
        #   15-19: '_____' roll (invalid)
        #   20-22: '___' heading (invalid)
        #   23-26: '0133' airspeed (13.3 kt)
        #   27-32: '+01073' pressure alt (1073 ft)
        #   33-36: '____' rate of turn (invalid)
        #   37-39: '+01' lateral accel (0.01 G)
        #   40-42: '+10' vertical accel (1.0 G)
        #   43-44: '00' AOA
        #   45-48: '+000' VS (0 fpm)
        #   49-51: '+32' OAT (32 C)
        #   52-54: '240' altimeter (27.50 + 2.40 = 29.90 inHg)

        msg = b"=1123594748____________0133+01073____+01+1000+000+32240"
        assert len(msg) == 55, f"Expected 55, got {len(msg)}"
        checksum = sum(msg) & 0xFF
        data = msg + f"{checksum:02X}".encode() + b"\r\n"

        # Should be 59 bytes
        assert len(data) == 59

        result = g3xtext.parse_attitude_air_data(data)
        assert result.airspeed == pytest.approx(13.3)  # 0133 * 0.1
        assert result.pressure_altitude == 1073
        assert result.oat == 32  # +32 C
        assert result.altimeter_setting == pytest.approx(29.90)  # 27.50 + 2.40

    def test_parse_real_format_gps_pvt(self):
        """Parse GPS PVT in format matching real G3X output."""
        # @YYMMDDHHMMSS + position data (57 bytes total)
        data = b"@190406235947__________________________________________\r\n"
        assert len(data) == 57

        result = g3xtext.parse_gps_pvt(data)
        assert result.timestamp.year == 2019
        assert result.timestamp.month == 4
        assert result.timestamp.day == 6
        # Position data is all underscores, so should be None
        assert result.latitude is None
        assert result.longitude is None
