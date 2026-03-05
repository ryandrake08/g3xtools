"""
Tests for g3xfplan.py - Flight route planning.

Critical aviation safety tests for haversine calculations, route finding,
and flight plan generation.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xfplan

# Constants
METERS_PER_NM = 1852.0


# --- Shared test fixtures ---


@pytest.fixture
def test_router(fixtures_dir):
    """Create a Router using the test NASR database with airports-only preferences."""
    import nasr

    original_path = nasr._NASR_MSGPACK_DATABASE_PATH
    nasr._NASR_MSGPACK_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

    try:
        waypoint_prefs = {
            "A": "INCLUDE",
            "VFR": "REJECT",
            "V": "REJECT",
            "N": "REJECT",
            "WP": "REJECT",
            "USER": "INCLUDE",
        }
        airway_prefs = {"V": "INCLUDE", "J": "INCLUDE", "TEST": "INCLUDE"}
        max_leg_meters = 50.0 * METERS_PER_NM  # 50nm forces stepping through chain
        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters)
        yield router
    finally:
        nasr._NASR_MSGPACK_DATABASE_PATH = original_path


@pytest.fixture
def airway_router(fixtures_dir):
    """Create a Router using the test NASR database with airway-compatible preferences.

    Includes WP (fix) type waypoints for testing airway route splitting where
    intermediate waypoints are navaids/fixes rather than airports.
    """
    import nasr

    original_path = nasr._NASR_MSGPACK_DATABASE_PATH
    nasr._NASR_MSGPACK_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

    try:
        waypoint_prefs = {
            "A": "INCLUDE",
            "VFR": "INCLUDE",
            "V": "INCLUDE",
            "N": "INCLUDE",
            "WP": "INCLUDE",
            "USER": "INCLUDE",
        }
        airway_prefs = {"V": "INCLUDE", "J": "INCLUDE", "TEST": "INCLUDE"}
        max_leg_meters = 80.0 * METERS_PER_NM
        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters)
        yield router
    finally:
        nasr._NASR_MSGPACK_DATABASE_PATH = original_path


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

    original_path = nasr._NASR_MSGPACK_DATABASE_PATH

    try:
        # Point to test database
        nasr._NASR_MSGPACK_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        # Initialize router with required parameters
        # Router(waypoint_preferences, airway_preferences, max_leg_length, user_waypoints)
        waypoint_prefs = {
            "A": "INCLUDE",  # Airports
            "VFR": "INCLUDE",  # VFR waypoints
            "V": "INCLUDE",  # VOR
            "N": "INCLUDE",  # NDB
            "WP": "INCLUDE",  # Fixes
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
        assert len(router.waypoints) == 13  # From test database
        assert len(router.airways) == 2
        assert len(router.connections) > 0

        # Verify waypoint data structure
        kaaa = router.waypoints[0]
        assert kaaa[0] == "KAAA"
        assert kaaa[1] == "A"  # Airport type

    finally:
        # Restore original path
        nasr._NASR_MSGPACK_DATABASE_PATH = original_path


def test_route_finds_path(fixtures_dir):
    """A* should find a path between connected waypoints."""
    import nasr

    original_path = nasr._NASR_MSGPACK_DATABASE_PATH

    try:
        nasr._NASR_MSGPACK_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        waypoint_prefs = {
            "A": "INCLUDE",
            "VFR": "INCLUDE",
            "V": "INCLUDE",
            "N": "INCLUDE",
            "WP": "INCLUDE",
            "USER": "INCLUDE",
        }
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
        nasr._NASR_MSGPACK_DATABASE_PATH = original_path


def test_user_waypoint_integration(fixtures_dir):
    """User waypoints should be properly integrated into routing."""
    import nasr

    original_path = nasr._NASR_MSGPACK_DATABASE_PATH

    try:
        nasr._NASR_MSGPACK_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        waypoint_prefs = {
            "A": "INCLUDE",
            "VFR": "INCLUDE",
            "V": "INCLUDE",
            "N": "INCLUDE",
            "WP": "INCLUDE",
            "USER": "INCLUDE",
        }
        airway_prefs = {"V": "INCLUDE", "J": "INCLUDE", "TEST": "INCLUDE"}
        max_leg_meters = 200.0 * METERS_PER_NM

        # Add user waypoint
        user_wpts = [("USR001", 40.25, -120.25)]
        router = g3xfplan.Router(waypoint_prefs, airway_prefs, max_leg_meters, user_waypoints=user_wpts)

        # Verify user waypoint added (should be at end of list)
        assert len(router.waypoints) == 14  # 13 original + 1 user

        # Find the user waypoint
        usr_wp = router.waypoints[-1]
        assert usr_wp[0] == "USR001"
        assert usr_wp[1] == "USER"
        assert usr_wp[2] == 40.25
        assert usr_wp[3] == -120.25

    finally:
        nasr._NASR_MSGPACK_DATABASE_PATH = original_path


def test_route_calculation_returns_waypoint_list(fixtures_dir):
    """Route calculation should return list of waypoint indices."""
    import nasr

    original_path = nasr._NASR_MSGPACK_DATABASE_PATH

    try:
        nasr._NASR_MSGPACK_DATABASE_PATH = fixtures_dir / "nasr_test.msgpack"

        waypoint_prefs = {
            "A": "INCLUDE",
            "VFR": "INCLUDE",
            "V": "INCLUDE",
            "N": "INCLUDE",
            "WP": "INCLUDE",
            "USER": "INCLUDE",
        }
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
        nasr._NASR_MSGPACK_DATABASE_PATH = original_path


# --- Flight splitting tests ---

# Test database waypoint indices:
# 0=KAAA, 1=KBBB, 2=VPTEST(VFR), 3=KCCC, 4=VORNAV(VOR), 5=NDBPT(NDB),
# 6=KDDD, 7=KEEE, 8=KFFF, 9=KGGG
# Chain: KAAA(0)→KBBB(1)→KCCC(3)→KDDD(6)→KEEE(7)→KFFF(8)→KGGG(9)
# Each segment ~37nm


def test_route_distance(test_router):
    """route_distance returns correct total distance in meters."""
    # Single segment KAAA→KBBB (~37nm)
    dist = g3xfplan.route_distance(test_router, [0, 1])
    assert 35 * METERS_PER_NM <= dist <= 40 * METERS_PER_NM

    # Two segments KAAA→KBBB→KCCC (~74nm)
    dist2 = g3xfplan.route_distance(test_router, [0, 1, 3])
    assert 70 * METERS_PER_NM <= dist2 <= 80 * METERS_PER_NM

    # Empty/single-point route has zero distance
    assert g3xfplan.route_distance(test_router, [0]) == 0.0
    assert g3xfplan.route_distance(test_router, []) == 0.0


def test_find_split_point(test_router):
    """find_split_point finds correct airport index in route."""
    # Route: KAAA(0)→KBBB(1)→KCCC(3)→KDDD(6)
    route = [0, 1, 3, 6]

    # With 100nm limit: should include KBBB(37nm) and KCCC(74nm), but KDDD(111nm) exceeds
    # So last airport before limit is KCCC at route index 2
    split_pos, airport_idx = g3xfplan.find_split_point(test_router, route, 100 * METERS_PER_NM, set())
    assert split_pos == 2  # KCCC
    assert airport_idx == route[split_pos]  # In-route airport

    # With 50nm limit: should include KBBB(37nm) but KCCC(74nm) exceeds
    # So last airport before limit is KBBB at route index 1
    split_pos, airport_idx = g3xfplan.find_split_point(test_router, route, 50 * METERS_PER_NM, set())
    assert split_pos == 1  # KBBB
    assert airport_idx == route[split_pos]  # In-route airport


def test_find_split_point_prefers_via_airport(test_router):
    """find_split_point prefers via airports as split points."""
    # Route: KAAA(0)→KBBB(1)→KCCC(3)→KDDD(6)
    route = [0, 1, 3, 6]

    # KBBB (index 1) is a via airport, KCCC (index 3) is not
    # With 100nm limit, both KBBB and KCCC are within limit
    # Should prefer KBBB because it's a via airport
    via_airport_indices = {1}  # KBBB is a via
    split_pos, airport_idx = g3xfplan.find_split_point(test_router, route, 100 * METERS_PER_NM, via_airport_indices)
    assert split_pos == 1  # Prefers via airport KBBB
    assert airport_idx == 1  # KBBB waypoint index


def test_find_split_point_no_airport(test_router):
    """find_split_point returns (-1, -1) when no airport found within limit."""
    # Route with only VFR waypoints between airports that are too far apart
    # KAAA(0)→VPTEST(2)→KBBB(1), but with very short limit
    route = [0, 2, 1]

    # With 10nm limit: VPTEST is at ~19nm but exceeds the 10nm limit immediately.
    # No position within limit (last_pos_before_limit stays at 0),
    # so no fallback search is attempted.
    split_pos, airport_idx = g3xfplan.find_split_point(test_router, route, 10 * METERS_PER_NM, set())
    assert (split_pos, airport_idx) == (-1, -1)


def test_split_no_split_needed(test_router):
    """Route within limit returns single flight."""
    route = [0, 1]  # KAAA→KBBB, ~37nm
    flights = g3xfplan.split_route_into_flights(
        test_router, route, 0, 1, [], 100 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_GREEDY
    )
    assert len(flights) == 1
    assert flights[0] == route


def test_split_greedy_basic(test_router):
    """Greedy strategy splits at airport boundaries."""
    # Full chain: KAAA→KBBB→KCCC→KDDD→KEEE→KFFF→KGGG (~222nm)
    route = [0, 1, 3, 6, 7, 8, 9]

    flights = g3xfplan.split_route_into_flights(
        test_router, route, 0, 9, [], 100 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_GREEDY
    )

    # Should produce multiple flights
    assert len(flights) >= 2

    # Each flight starts at an airport and ends at an airport
    for flight in flights:
        assert test_router.waypoints[flight[0]][1] in g3xfplan.SPLIT_AIRPORT_TYPES
        assert test_router.waypoints[flight[-1]][1] in g3xfplan.SPLIT_AIRPORT_TYPES

    # Each flight's distance should be <= 100nm (with some tolerance for via preference)
    for flight in flights:
        dist = g3xfplan.route_distance(test_router, flight) / METERS_PER_NM
        assert dist <= 110, f"Flight too long: {dist:.1f}nm"

    # Last waypoint of flight N = first waypoint of flight N+1
    for i in range(len(flights) - 1):
        assert flights[i][-1] == flights[i + 1][0]

    # First flight starts at origin, last flight ends at destination
    assert flights[0][0] == 0  # KAAA
    assert flights[-1][-1] == 9  # KGGG


def test_split_recompute_basic(test_router):
    """Recompute strategy splits with fresh A* calls."""
    # Use the chain route
    route = [0, 1, 3, 6, 7, 8, 9]

    flights = g3xfplan.split_route_into_flights(
        test_router, route, 0, 9, [], 100 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_RECOMPUTE
    )

    # Should produce multiple flights
    assert len(flights) >= 2

    # Each flight starts and ends at an airport
    for flight in flights:
        assert test_router.waypoints[flight[0]][1] in g3xfplan.SPLIT_AIRPORT_TYPES
        assert test_router.waypoints[flight[-1]][1] in g3xfplan.SPLIT_AIRPORT_TYPES

    # Last waypoint of flight N = first waypoint of flight N+1
    for i in range(len(flights) - 1):
        assert flights[i][-1] == flights[i + 1][0]

    # Endpoints preserved
    assert flights[0][0] == 0  # KAAA
    assert flights[-1][-1] == 9  # KGGG


def test_split_no_intermediate_airport_warns(test_router, capsys):
    """Warns on stderr when no airport found within limit."""
    # Route with only non-airport waypoints between origin and destination
    # KAAA(0)→VPTEST(2)→KBBB(1), with very short limit
    route = [0, 2, 1]

    flights = g3xfplan.split_route_greedy(test_router, route, 10 * METERS_PER_NM, set())

    # Should include the over-length leg and warn
    assert len(flights) == 1
    assert flights[0] == route

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "no airport found" in captured.err


def test_split_equal_lengths(test_router):
    """Equal lengths distributes distance more evenly than default splitting."""
    route = [0, 1, 3, 6, 7, 8, 9]  # ~225nm chain

    # With 200nm max, default greedy produces ~188nm + ~37nm (very unbalanced)
    flights_default = g3xfplan.split_route_into_flights(
        test_router, route, 0, 9, [], 200 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_GREEDY, equal_lengths=False
    )

    # With equal_lengths, target becomes ~112.5nm, producing ~75nm + ~150nm (more balanced)
    flights_equal = g3xfplan.split_route_into_flights(
        test_router, route, 0, 9, [], 200 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_GREEDY, equal_lengths=True
    )

    assert len(flights_equal) >= 2
    assert len(flights_default) >= 2

    # Compute distances
    distances_default = [g3xfplan.route_distance(test_router, f) / METERS_PER_NM for f in flights_default]
    distances_equal = [g3xfplan.route_distance(test_router, f) / METERS_PER_NM for f in flights_equal]

    # Equal flights should be more balanced (lower ratio of longest to shortest)
    ratio_default = max(distances_default) / min(distances_default)
    ratio_equal = max(distances_equal) / min(distances_equal)
    assert ratio_equal < ratio_default, (
        f"Equal flights not more balanced: equal={distances_equal} (ratio {ratio_equal:.2f}) "
        f"vs default={distances_default} (ratio {ratio_default:.2f})"
    )

    # All flights should still be <= original max_flight_length
    for d in distances_equal:
        assert d <= 210, f"Flight exceeds max: {d:.1f}nm"

    # Continuity check
    for i in range(len(flights_equal) - 1):
        assert flights_equal[i][-1] == flights_equal[i + 1][0]


def test_fpl_numbered_output(test_router, tmp_path):
    """Multiple flights generate numbered FPL files."""
    import fpl

    route = [0, 1, 3, 6, 7, 8, 9]

    flights = g3xfplan.split_route_into_flights(
        test_router, route, 0, 9, [], 100 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_GREEDY
    )

    assert len(flights) >= 2, "Need multiple flights for this test"

    # Simulate FPL output for each flight (matching main() logic)
    base_path = tmp_path / "test.fpl"
    for flight_num, flight_route in enumerate(flights, 1):
        fpl_path = base_path.with_stem(f"{base_path.stem}_{flight_num}")

        route_data = []
        for idx in flight_route:
            wp = test_router.waypoints[idx]
            waypoint_id = wp[5] if len(wp) > 5 and wp[5] else wp[0]
            fpl_type = g3xfplan.WAYPOINT_TYPE_MAP.get(wp[1], fpl.WAYPOINT_TYPE_USER)
            country = g3xfplan.COUNTRY_CODE_MAP.get(wp[4], '')
            route_data.append((waypoint_id, wp[2], wp[3], fpl_type, country))

        flight_plan = fpl.create_flight_plan_from_route_list(route_data)
        fpl.write_fpl(flight_plan, fpl_path)

    # Verify numbered files exist
    for i in range(1, len(flights) + 1):
        assert (tmp_path / f"test_{i}.fpl").exists(), f"test_{i}.fpl should exist"

    # Original (unnumbered) file should NOT exist
    assert not (tmp_path / "test.fpl").exists()


# --- Airway route splitting tests (nearby airport fallback) ---

# Fix chain waypoint indices:
# 10=FIXAB(WP), 11=FIXBC(WP), 12=FIXCD(WP)
# Fix chain route: KAAA(0)→FIXAB(10)→FIXBC(11)→FIXCD(12)→KDDD(6)
# Segments: 0→10 ~19nm, 10→11 ~37nm, 11→12 ~37nm, 12→6 ~19nm, total ~112nm
# Nearby airports: KBBB(1) ~19nm from FIXBC(11), KCCC(3) ~19nm from FIXBC(11)


def test_find_nearest_airport(airway_router):
    """find_nearest_airport finds an airport near a navaid."""
    # FIXBC(11) at (40.75, -120.75) is ~19nm from KBBB(1) at (40.5, -120.5)
    # and ~19nm from KCCC(3) at (41.0, -121.0)
    result = g3xfplan.find_nearest_airport(airway_router, 11, 50 * METERS_PER_NM)
    assert result >= 0, "Should find a nearby airport"
    assert airway_router.waypoints[result][1] in g3xfplan.SPLIT_AIRPORT_TYPES


def test_find_nearest_airport_no_result(airway_router):
    """find_nearest_airport returns -1 with tiny search radius."""
    # Search within 1nm of FIXBC - no airport should be that close
    result = g3xfplan.find_nearest_airport(airway_router, 11, 1 * METERS_PER_NM)
    assert result == -1


def test_find_split_point_nearby_airport_fallback(airway_router):
    """find_split_point falls back to nearby airport when none in route."""
    # Route through fixes only (no intermediate airports):
    # KAAA(0)→FIXAB(10)→FIXBC(11)→FIXCD(12)→KDDD(6)
    route = [0, 10, 11, 12, 6]

    # With 60nm limit:
    # 0→10: ~19nm (FIXAB, not airport, within limit)
    # 10→11: ~37nm, cumulative ~56nm (FIXBC, not airport, within limit)
    # 11→12: ~37nm, cumulative ~93nm → exceeds limit
    # No airport found in route, but KBBB or KCCC are nearby FIXBC
    split_pos, airport_idx = g3xfplan.find_split_point(airway_router, route, 60 * METERS_PER_NM, set())

    # Should find a nearby airport (off-route fallback)
    assert split_pos > 0, "Should have a valid split position"
    assert airport_idx >= 0, "Should find a nearby airport"
    assert airway_router.waypoints[airport_idx][1] in g3xfplan.SPLIT_AIRPORT_TYPES
    # Airport is NOT in the route (off-route fallback)
    assert airport_idx != route[split_pos]


def test_split_greedy_airway_route(airway_router):
    """Greedy strategy splits airway-style route using nearby airports."""
    # Route through fixes only (simulates airway routing):
    # KAAA(0)→FIXAB(10)→FIXBC(11)→FIXCD(12)→KDDD(6)
    route = [0, 10, 11, 12, 6]

    flights = g3xfplan.split_route_greedy(airway_router, route, 60 * METERS_PER_NM, set())

    # Should produce multiple flights
    assert len(flights) >= 2, f"Expected multiple flights, got {len(flights)}"

    # First flight should start at KAAA
    assert flights[0][0] == 0  # KAAA

    # Last flight should end at KDDD
    assert flights[-1][-1] == 6  # KDDD

    # Each flight should start and end at an airport
    for i, flight in enumerate(flights):
        assert (
            airway_router.waypoints[flight[0]][1] in g3xfplan.SPLIT_AIRPORT_TYPES
        ), f"Flight {i+1} start {airway_router.waypoints[flight[0]][0]} is not an airport"
        assert (
            airway_router.waypoints[flight[-1]][1] in g3xfplan.SPLIT_AIRPORT_TYPES
        ), f"Flight {i+1} end {airway_router.waypoints[flight[-1]][0]} is not an airport"

    # Last waypoint of flight N = first waypoint of flight N+1 (continuity)
    for i in range(len(flights) - 1):
        assert flights[i][-1] == flights[i + 1][0], f"Flight {i+1} end != Flight {i+2} start"


def test_split_greedy_always_splits_at_via_airports(test_router):
    """Via airports are always used as split points even when remaining distance fits."""
    # Route: KAAA(0)→KBBB(1)→KCCC(3)→KDDD(6), total ~111nm
    # With 200nm limit, the whole route fits — but KBBB is a via airport,
    # so it should still produce a split there.
    route = [0, 1, 3, 6]
    via_ids = [1]  # KBBB is a via
    flights = g3xfplan.split_route_into_flights(
        test_router, route, 0, 6, via_ids, 200 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_GREEDY
    )

    assert len(flights) >= 2, "Should split at via airport even when route fits"
    # First flight must end at KBBB (the via)
    assert flights[0][-1] == 1, "First flight should end at via airport KBBB"
    # Second flight starts at KBBB
    assert flights[1][0] == 1, "Second flight should start at via airport KBBB"
    # Endpoints preserved
    assert flights[0][0] == 0  # KAAA
    assert flights[-1][-1] == 6  # KDDD


def test_split_recompute_always_splits_at_via_airports(test_router):
    """Via airports are always used as split points in recompute strategy too."""
    route = [0, 1, 3, 6]
    via_ids = [1]  # KBBB is a via
    flights = g3xfplan.split_route_into_flights(
        test_router, route, 0, 6, via_ids, 200 * METERS_PER_NM, g3xfplan.SPLIT_STRATEGY_RECOMPUTE
    )

    assert len(flights) >= 2, "Should split at via airport even when route fits"
    # First flight must end at KBBB (the via)
    assert flights[0][-1] == 1, "First flight should end at via airport KBBB"
    assert flights[1][0] == 1
    assert flights[0][0] == 0
    assert flights[-1][-1] == 6
