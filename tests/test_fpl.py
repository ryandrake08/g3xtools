"""
Tests for fpl.py - Garmin Flight Plan format.

Critical aviation safety tests for FPL file reading, writing, and validation.
"""

import pytest

import fpl


def test_read_simple_fpl(fixtures_dir):
    """Read a simple 2-waypoint FPL file."""
    fpl_path = fixtures_dir / "simple_route.fpl"
    flight_plan = fpl.read_fpl(fpl_path)

    assert flight_plan.route
    assert flight_plan.route.route_name == "TEST ROUTE"
    assert flight_plan.route.flight_plan_index == 1
    assert len(flight_plan.waypoint_table) == 2
    assert len(flight_plan.route.route_points) == 2

    # Check first waypoint
    wpt1 = flight_plan.waypoint_table[0]
    assert wpt1.identifier == "KAAA"
    assert wpt1.type == "AIRPORT"
    assert wpt1.country_code == "US"
    assert wpt1.lat == 40.0
    assert wpt1.lon == -120.0


def test_round_trip_fpl(tmp_path, fixtures_dir):
    """FPL round-trip: read → write → read should produce identical data."""
    original_path = fixtures_dir / "simple_route.fpl"
    temp_path = tmp_path / "temp.fpl"

    # Read original
    original_fp = fpl.read_fpl(original_path)

    # Write to temp
    fpl.write_fpl(original_fp, temp_path)

    # Read temp
    roundtrip_fp = fpl.read_fpl(temp_path)

    # Compare
    assert roundtrip_fp.route
    assert original_fp.route
    assert roundtrip_fp.route.route_name == original_fp.route.route_name
    assert roundtrip_fp.route.flight_plan_index == original_fp.route.flight_plan_index
    assert len(roundtrip_fp.waypoint_table) == len(original_fp.waypoint_table)
    assert len(roundtrip_fp.route.route_points) == len(original_fp.route.route_points)

    # Check waypoint data preservation
    for orig_wpt, rt_wpt in zip(original_fp.waypoint_table, roundtrip_fp.waypoint_table):
        assert orig_wpt.identifier == rt_wpt.identifier
        assert orig_wpt.type == rt_wpt.type
        assert orig_wpt.country_code == rt_wpt.country_code
        assert orig_wpt.lat == rt_wpt.lat
        assert orig_wpt.lon == rt_wpt.lon
        assert orig_wpt.comment == rt_wpt.comment


def test_waypoint_coordinate_precision(tmp_path):
    """Ensure coordinates maintain 6 decimal places (±0.11m accuracy)."""
    # Create waypoint with high precision
    # Signature: create_waypoint(identifier, lat, lon, waypoint_type, country_code, comment, ...)
    waypoint = fpl.create_waypoint("TEST", 37.123456, -122.987654, fpl.WAYPOINT_TYPE_AIRPORT, "US", "PRECISION TEST")

    # Create minimal flight plan
    # create_route(name, waypoint_refs, flight_plan_index, route_description)
    # waypoint_refs is list of (identifier, type, country_code) tuples
    route = fpl.create_route("PRECISION TEST", [("TEST", fpl.WAYPOINT_TYPE_AIRPORT, "US")], flight_plan_index=1)
    flight_plan = fpl.create_flight_plan([waypoint], route)

    # Write and read back
    temp_path = tmp_path / "precision.fpl"
    fpl.write_fpl(flight_plan, temp_path)
    roundtrip = fpl.read_fpl(temp_path)

    # Check precision maintained
    rt_wpt = roundtrip.waypoint_table[0]
    assert rt_wpt.lat == 37.123456
    assert rt_wpt.lon == -122.987654


def test_user_waypoint_handling(fixtures_dir):
    """User waypoints should have empty country code."""
    fpl_path = fixtures_dir / "user_waypoint.fpl"
    flight_plan = fpl.read_fpl(fpl_path)

    # Find the user waypoint
    # get_waypoint signature: (flight_plan, identifier, waypoint_type, country_code)
    usr_wpt = fpl.get_waypoint(flight_plan, "USR001", fpl.WAYPOINT_TYPE_USER, "")
    assert usr_wpt is not None
    assert usr_wpt.type == fpl.WAYPOINT_TYPE_USER
    assert usr_wpt.country_code == ""
    assert usr_wpt.comment == "USER WAYPOINT 1"


def test_route_point_references_validation(fixtures_dir):
    """Route points must reference existing waypoints (XSD keyref validation)."""
    fpl_path = fixtures_dir / "invalid_route.fpl"

    # This file has a route point referencing non-existent waypoint "NONEXISTENT"
    # Without validation, this should read successfully
    flight_plan = fpl.read_fpl(fpl_path, validate=False)
    assert flight_plan.route
    assert len(flight_plan.route.route_points) == 2

    # With validation enabled, should raise error
    with pytest.raises(ValueError, match="references non-existent waypoint"):
        fpl.validate_flight_plan(flight_plan)


def test_flight_plan_index_range():
    """Flight plan index must be 1-98."""
    # create_route(name, waypoint_refs, flight_plan_index, route_description)
    # Valid index
    route = fpl.create_route("TEST", [], flight_plan_index=1)
    assert route.flight_plan_index == 1

    route = fpl.create_route("TEST", [], flight_plan_index=98)
    assert route.flight_plan_index == 98

    # Invalid indices should raise ValueError when validated
    # Note: create_route doesn't validate, but validate_flight_plan_index does
    with pytest.raises(ValueError, match="between 1 and 98"):
        fpl.validate_flight_plan_index(0)

    with pytest.raises(ValueError, match="between 1 and 98"):
        fpl.validate_flight_plan_index(99)


def test_country_code_validation():
    """Country codes must be 2 alphanumeric characters or empty."""
    # Valid country codes (create_waypoint doesn't validate, test validate_country_code directly)
    fpl.validate_country_code("US")
    fpl.validate_country_code("K2")
    fpl.validate_country_code("")

    # Invalid country codes should raise ValueError
    with pytest.raises(ValueError, match="Invalid country code"):
        fpl.validate_country_code("USA")

    with pytest.raises(ValueError, match="Invalid country code"):
        fpl.validate_country_code("U")

    with pytest.raises(ValueError, match="Invalid country code"):
        fpl.validate_country_code("us")  # Must be uppercase


def test_waypoint_type_validation():
    """Only valid waypoint types should be accepted."""
    # Valid types (test validate_waypoint_type directly)
    valid_types = [
        fpl.WAYPOINT_TYPE_USER,
        fpl.WAYPOINT_TYPE_AIRPORT,
        fpl.WAYPOINT_TYPE_NDB,
        fpl.WAYPOINT_TYPE_VOR,
        fpl.WAYPOINT_TYPE_INT,
        fpl.WAYPOINT_TYPE_INT_VRP,
    ]

    for wpt_type in valid_types:
        fpl.validate_waypoint_type(wpt_type)

    # Invalid type
    with pytest.raises(ValueError, match="Invalid waypoint type"):
        fpl.validate_waypoint_type("INVALID")


def test_route_name_validation():
    """Route names must be 0-25 uppercase alphanumeric/spaces/slashes."""
    # Valid route names (test validate_route_name directly)
    fpl.validate_route_name("A")
    fpl.validate_route_name("A" * 25)
    fpl.validate_route_name("TEST/ROUTE")
    fpl.validate_route_name("")  # Empty is valid per pattern

    # Invalid route names
    with pytest.raises(ValueError, match="Invalid route name"):
        fpl.validate_route_name("A" * 26)  # Too long

    with pytest.raises(ValueError, match="Invalid route name"):
        fpl.validate_route_name("test")  # Lowercase not allowed


def test_create_flight_plan_from_route_list():
    """Test helper function for creating flight plans from route lists."""
    # Signature: (identifier, lat, lon, waypoint_type, country_code)
    route_data = [
        ("KAAA", 40.0, -120.0, fpl.WAYPOINT_TYPE_AIRPORT, "US"),
        ("KBBB", 40.5, -120.5, fpl.WAYPOINT_TYPE_AIRPORT, "US"),
    ]

    flight_plan = fpl.create_flight_plan_from_route_list(route_data, "TEST")

    assert len(flight_plan.waypoint_table) == 2
    assert flight_plan.route
    assert len(flight_plan.route.route_points) == 2
    assert flight_plan.route.route_name == "TEST"
    assert flight_plan.route.flight_plan_index == 1


def test_get_waypoint_helper():
    """Test get_waypoint helper function."""
    waypoints = [
        fpl.create_waypoint("KAAA", 40.0, -120.0, fpl.WAYPOINT_TYPE_AIRPORT, "US"),
        fpl.create_waypoint("KBBB", 40.5, -120.5, fpl.WAYPOINT_TYPE_AIRPORT, "US"),
    ]
    route = fpl.create_route("TEST", [], flight_plan_index=1)
    flight_plan = fpl.create_flight_plan(waypoints, route)

    # Found - get_waypoint(flight_plan, identifier, waypoint_type, country_code)
    wpt = fpl.get_waypoint(flight_plan, "KAAA", fpl.WAYPOINT_TYPE_AIRPORT, "US")
    assert wpt is not None
    assert wpt.identifier == "KAAA"

    # Not found
    wpt = fpl.get_waypoint(flight_plan, "NONEXISTENT", fpl.WAYPOINT_TYPE_AIRPORT, "US")
    assert wpt is None
