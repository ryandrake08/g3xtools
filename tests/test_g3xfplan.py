"""
Tests for g3xfplan.py - Flight route planning.

Critical aviation safety tests for haversine calculations, route finding,
and flight plan generation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xfplan

# Constants
METERS_PER_NM = 1852.0


def test_haversine_known_distances():
    """Test haversine against known distances."""
    # Test with synthetic coordinates from test fixtures
    # KAAA (40.0, -120.0) to KBBB (40.5, -120.5)
    distance_meters = g3xfplan.haversine(40.0, -120.0, 40.5, -120.5)
    distance_nm = distance_meters / METERS_PER_NM

    # Verify distance is approximately correct
    # Actual calculation: ~37.76nm for 0.5 degree diagonal at 40° latitude
    assert 35 <= distance_nm <= 40, f"Expected ~37-38nm, got {distance_nm:.2f}nm"

    # Test zero distance (same point)
    distance_zero = g3xfplan.haversine(40.0, -120.0, 40.0, -120.0)
    assert distance_zero == 0.0

    # Test symmetry
    d1 = g3xfplan.haversine(37.5, -122.5, 38.5, -121.5)
    d2 = g3xfplan.haversine(38.5, -121.5, 37.5, -122.5)
    assert d1 == d2, "Haversine should be symmetric"


def test_bounding_box():
    """Test bounding box calculation for spatial queries."""
    # Center point with 50nm radius (in meters)
    center_lat, center_lon = 40.0, -120.0
    radius_meters = 50.0 * METERS_PER_NM

    # Returns: (NE_lat, NE_lon, SW_lat, SW_lon)
    ne_lat, ne_lon, sw_lat, sw_lon = g3xfplan.bounding_box(center_lat, center_lon, radius_meters)

    # NE corner should be north and east of center
    assert ne_lat >= center_lat
    assert ne_lon >= center_lon

    # SW corner should be south and west of center
    assert sw_lat <= center_lat
    assert sw_lon <= center_lon

    # Bounding box should contain center point
    assert sw_lat <= center_lat <= ne_lat
    assert sw_lon <= center_lon <= ne_lon


def test_router_initialization_with_test_nasr(fixtures_dir):
    """Initialize Router with test NASR database."""
    # Temporarily set NASR database path for testing
    import nasr

    original_path = nasr._NASR_DATABASE_PATH

    try:
        # Point to test database
        nasr._NASR_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        # Initialize router with required parameters
        # Router(waypoint_preferences, airway_preferences, max_leg_length, user_waypoints)
        waypoint_prefs = {
            "A": "INCLUDE",  # Airports
            "VFR": "INCLUDE",  # VFR waypoints
            "V": "INCLUDE",  # VOR
            "N": "INCLUDE",  # NDB
            "USER": "INCLUDE",  # User waypoints
        }
        airway_prefs = {
            "V": "INCLUDE",  # Victor airways
            "J": "INCLUDE",  # Jet airways
            "TEST": "INCLUDE",  # Test airway
        }
        max_leg_meters = 200.0 * METERS_PER_NM  # 200nm

        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters)

        # Verify data loaded
        assert len(router.waypoints) == 6  # From test database
        assert len(router.airways) == 2
        assert len(router.connections) > 0

        # Verify waypoint data structure
        kaaa = router.waypoints[0]
        assert kaaa[0] == "KAAA"
        assert kaaa[1] == "A"  # Airport type

    finally:
        # Restore original path
        nasr._NASR_DATABASE_PATH = original_path


def test_route_finds_path(fixtures_dir):
    """A* should find a path between connected waypoints."""
    import nasr

    original_path = nasr._NASR_DATABASE_PATH

    try:
        nasr._NASR_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        waypoint_prefs = {"A": "INCLUDE", "VFR": "INCLUDE", "V": "INCLUDE", "N": "INCLUDE", "USER": "INCLUDE"}
        airway_prefs = {"V": "INCLUDE", "J": "INCLUDE", "TEST": "INCLUDE"}
        max_leg_meters = 200.0 * METERS_PER_NM

        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters)

        # Find route from KAAA (index 0) to KBBB (index 1)
        routes_iterator = router.astar(0, 1)
        assert routes_iterator
        route = list(routes_iterator)

        assert route is not None and len(route) > 0, "Should find route between connected waypoints"
        assert route[0] == 0, "Route should start at origin"
        assert route[-1] == 1, "Route should end at destination"

    finally:
        nasr._NASR_DATABASE_PATH = original_path


def test_user_waypoint_integration(fixtures_dir):
    """User waypoints should be properly integrated into routing."""
    import nasr

    original_path = nasr._NASR_DATABASE_PATH

    try:
        nasr._NASR_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        waypoint_prefs = {"A": "INCLUDE", "VFR": "INCLUDE", "V": "INCLUDE", "N": "INCLUDE", "USER": "INCLUDE"}
        airway_prefs = {"V": "INCLUDE", "J": "INCLUDE", "TEST": "INCLUDE"}
        max_leg_meters = 200.0 * METERS_PER_NM

        # Add user waypoint
        user_wpts = [("USR001", 40.25, -120.25)]
        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters, user_waypoints=user_wpts)

        # Verify user waypoint added (should be at end of list)
        assert len(router.waypoints) == 7  # 6 original + 1 user

        # Find the user waypoint
        usr_wp = router.waypoints[-1]
        assert usr_wp[0] == "USR001"
        assert usr_wp[1] == "USER"
        assert usr_wp[2] == 40.25
        assert usr_wp[3] == -120.25

    finally:
        nasr._NASR_DATABASE_PATH = original_path


def test_route_calculation_returns_waypoint_list(fixtures_dir):
    """Route calculation should return list of waypoint indices."""
    import nasr

    original_path = nasr._NASR_DATABASE_PATH

    try:
        nasr._NASR_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        waypoint_prefs = {"A": "INCLUDE", "VFR": "INCLUDE", "V": "INCLUDE", "N": "INCLUDE", "USER": "INCLUDE"}
        airway_prefs = {"V": "INCLUDE", "J": "INCLUDE", "TEST": "INCLUDE"}
        max_leg_meters = 200.0 * METERS_PER_NM

        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters)

        routes_iterator = router.astar(0, 1)
        assert routes_iterator
        route = list(routes_iterator)

        assert isinstance(route, list), "Route should be a list"
        assert all(isinstance(x, int) for x in route), "Route should contain integers"
        assert all(0 <= x < len(router.waypoints) for x in route), "Indices should be valid"

    finally:
        nasr._NASR_DATABASE_PATH = original_path
