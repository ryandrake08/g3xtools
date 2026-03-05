#!/usr/bin/env python3

import argparse
import itertools
import math
import pathlib
import sys
import urllib.parse
import webbrowser
from typing import Optional, Union

try:
    import astar
except ImportError:
    print("Error: astar is required. Install with: pip install 'g3xtools[fplan]'", file=sys.stderr)
    sys.exit(1)

try:
    import rtree
except ImportError:
    print("Error: rtree is required. Install with: pip install 'g3xtools[fplan]'", file=sys.stderr)
    sys.exit(1)

import fpl
import nasr

# Geographic constants
EARTH_RADIUS_METERS = 6371000  # Mean radius of Earth in meters

# Flight planning defaults
DEFAULT_MAX_LEG_LENGTH_NM = 80  # Default maximum leg length for VFR routing

# All aerodrome-type waypoint codes (used for waypoint lookup and FPL type mapping)
AIRPORT_TYPES = frozenset(('A', 'B', 'C', 'G', 'H', 'U'))

# Only land airports are valid split points for multi-flight routes
SPLIT_AIRPORT_TYPES = frozenset(('A',))

# Flight split strategies
SPLIT_STRATEGY_GREEDY = 'greedy'
SPLIT_STRATEGY_RECOMPUTE = 'recompute'

# Map NASR waypoint types to FPL waypoint types
WAYPOINT_TYPE_MAP = {
    'A': fpl.WAYPOINT_TYPE_AIRPORT,
    'B': fpl.WAYPOINT_TYPE_AIRPORT,  # unconfirmed
    'C': fpl.WAYPOINT_TYPE_AIRPORT,
    'G': fpl.WAYPOINT_TYPE_AIRPORT,
    'H': fpl.WAYPOINT_TYPE_AIRPORT,
    'U': fpl.WAYPOINT_TYPE_AIRPORT,
    'DME': fpl.WAYPOINT_TYPE_VOR,
    'NDB': fpl.WAYPOINT_TYPE_NDB,
    'NDB/DME': fpl.WAYPOINT_TYPE_NDB,
    'VOR': fpl.WAYPOINT_TYPE_VOR,
    'VORTAC': fpl.WAYPOINT_TYPE_VOR,
    'VOR/DME': fpl.WAYPOINT_TYPE_VOR,
    'VFR': fpl.WAYPOINT_TYPE_INT,
    'CN': fpl.WAYPOINT_TYPE_INT,  # unconfirmed
    'MR': fpl.WAYPOINT_TYPE_INT,
    'RP': fpl.WAYPOINT_TYPE_INT,
    'WP': fpl.WAYPOINT_TYPE_INT,
    'USER': fpl.WAYPOINT_TYPE_USER,
}

# Map NASR country codes to FPL country codes
COUNTRY_CODE_MAP = {
    'US': "K2",  # With some exceptions, Garmin seems to use K2 for country code in the .fpl file
    'CA': "CY",  # Found on the Internet. Unconfirmed
    '': '',  # User waypoints are always blank country code
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth's surface using the Haversine formula.
    This formula assumes a spherical earth, which is accurate enough to calculate a-star neighbors and costs.
    If we were to use this for actual navigation, we would need to use the Vincenty formula for greater accuracy.

    Args:
        lat1 (float): Latitude of the first point in degrees.
        lon1 (float): Longitude of the first point in degrees.
        lat2 (float): Latitude of the second point in degrees.
        lon2 (float): Longitude of the second point in degrees.

    Returns:
        float: Distance between the two points in meters.
    """

    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    d = 2 * math.asin(math.sqrt(a))

    # Convert from angular distance to meters
    return d * EARTH_RADIUS_METERS


def bounding_box(lat1: float, lon1: float, distance: float) -> tuple[float, float, float, float]:
    """
    Calculate the bounding box coordinates (northeast and southwest corners)
    given a central point and a distance.

    Args:
        lat1 (float): Latitude of the central point in degrees.
        lon1 (float): Longitude of the central point in degrees.
        distance (float): Distance from the central point in meters.

    Returns:
        tuple: A tuple containing four float values:
            - Latitude of the northeast corner in degrees.
            - Longitude of the northeast corner in degrees.
            - Latitude of the southwest corner in degrees.
            - Longitude of the southwest corner in degrees.
    """

    # Convert latitude and longitude from degrees to radians
    lat1, lon1 = map(math.radians, [lat1, lon1])

    # Convert from meters to angular distance
    d = distance / EARTH_RADIUS_METERS

    # Shortcut for 45 and 225 degree bearings
    root1_2 = 0.7071067811865476  # sqrt(0.5)

    # Northeast bearing
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * root1_2)
    dlon2 = math.atan2(root1_2 * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    lon2 = lon1 + dlon2

    # Southwest bearing
    lat3 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * -root1_2)
    dlon3 = math.atan2(-root1_2 * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat3))
    lon3 = lon1 + dlon3

    # Convert latitude and longitude back to degrees
    return (math.degrees(lat2), math.degrees(lon2), math.degrees(lat3), math.degrees(lon3))


class Router(astar.AStar):
    '''
    Router class for implementing the A* pathfinding algorithm for aviation navigation.
    This class extends the AStar class and provides methods to calculate distances,
    find neighbors, and estimate costs for waypoints in an aviation routing context.

    Attributes:
        waypoints (list): A list of waypoints loaded from 'waypoints.pickle'.
        airways (list): A list of airways loaded from 'airways.pickle'.
        connections (dict): A dictionary of connections between waypoints loaded from 'connections.pickle'.
        waypoint_preferences (dict): A dictionary mapping waypoint types to routing preferences.
        airway_preferences (dict): A dictionary mapping airway types to routing preferences.
        max_leg_length (float): The maximum allowable length for any leg of the route.
        costs (dict): A dictionary mapping route preferences to cost modifiers.
        waypoints_idx (rtree.index.Index): An R-tree index for spatial queries on waypoints.

    Methods:
        __init__(waypoint_preferences, airway_preferences, max_leg_length):
            Initializes the Router with waypoint and airway preferences and maximum leg length.
        actual_distance_between(n1, n2):
            Calculates the actual distance between two waypoints using the Haversine formula.
        neighbors(node):
            Finds and returns the neighboring waypoints for a given node within max_leg_length meters.
        distance_between(n1, n2):
            Calculates the A* weighted distance between two waypoints.
        heuristic_cost_estimate(current, goal):
            Estimates the heuristic cost between the current waypoint and the goal waypoint.
    '''

    def __init__(self, waypoint_preferences, airway_preferences, max_leg_length, user_waypoints=None):
        """
        Initialize all the state needed to implement the a-star pathfinding algorithm.

        Args:
            waypoint_preferences (dict): A dictionary mapping waypoint types to routing preferences.
                                         Possible values are PREFER, INCLUDE, AVOID, and REJECT.
            max_leg_length (float): The maximum allowable length for any leg of the route.
            user_waypoints (list): Optional list of user waypoints to add. Each entry is (id, lat, lon).
        """

        # Load database
        database = nasr.load_nasr_database()
        self.waypoints = database['waypoints']
        self.airways = database['airways']
        self.connections = database['connections']

        # Add user waypoints to the waypoints list
        # User waypoint structure: [id, type, lat, lon, country] - country is empty string for user waypoints
        if user_waypoints:
            for wp_id, lat, lon in user_waypoints:
                self.waypoints.append([wp_id, 'USER', lat, lon, ''])

        # Store the route preferences
        self.waypoint_preferences = waypoint_preferences
        self.airway_preferences = airway_preferences
        self.max_leg_length = max_leg_length

        # Set costs for each route preference
        self.costs = {'PREFER': 0.8, 'INCLUDE': 1.0, 'AVOID': 1.25, 'REJECT': 1000.0}

        # Cache for bounding box calculations keyed by waypoint index
        self._bounding_box_cache = {}

        # Construct an rtree index
        def generator_function():
            for waypoint_id, waypoint in enumerate(self.waypoints):
                if waypoint_preferences[waypoint[1]] != 'REJECT':
                    yield (waypoint_id, (waypoint[3], waypoint[2], waypoint[3], waypoint[2]), None)

        self.waypoints_idx = rtree.index.Index(generator_function())

    def _get_cached_bounding_box(self, waypoint_index):
        """Get cached bounding box or calculate and cache it."""
        if waypoint_index not in self._bounding_box_cache:
            lat, lon = self.waypoints[waypoint_index][2:4]
            self._bounding_box_cache[waypoint_index] = bounding_box(lat, lon, self.max_leg_length)

        return self._bounding_box_cache[waypoint_index]

    def actual_distance_between(self, n1, n2):
        """
        Calculate the actual distance in between two waypoints using the Haversine formula.

        Args:
            n1 (int): The index of the first waypoint.
            n2 (int): The index of the second waypoint.

        Returns:
            float: The distance between the two waypoints in meters.
        """

        # Trivial case: same node
        if n1 == n2:
            return 0

        # Get information about each node from the cache
        lat1, lon1 = self.waypoints[n1][2:4]
        lat2, lon2 = self.waypoints[n2][2:4]

        # Calculate the distance between the two points
        return haversine(lat1, lon1, lat2, lon2)

    def neighbors(self, node):
        """
        Find and return the neighboring waypoints for a given node.
        For the purposes of aviation navigation, we will consider waypoints within
        max_leg_length meters of the given waypoint to be neighbors. To simplify
        and speed up this lookup, we calculate a bounding box around the waypoint
        and query the rtree index for waypoints within that bounding box. This will
        overestimate the neighbors, but that is acceptable for the purposes of the
        a-star algorithm.

        Required implementation of the abstract method in the astar class.

        Args:
            node (int): The index of the current waypoint.

        Returns:
            list: A list of indices of neighboring waypoints within a bounding box.
        """

        # Get cached bounding box using waypoint index
        north, east, south, west = self._get_cached_bounding_box(node)

        # Query the index for neighbors
        neighbors = list(self.waypoints_idx.intersection((west, south, east, north)))

        if self.airway_preferences:
            # Find airway neighbors, which should be included if we are using airways
            airway_neighbors = self.connections.get(node, [])

            # Add airway connections to neighbors
            neighbors.extend(neighbor for neighbor, _ in airway_neighbors if neighbor not in neighbors)

        return neighbors

    def distance_between(self, n1, n2):
        """
        Calculate the a-star weighted distance between two nodes.

        This method calculates the distance between two waypoints (nodes) and
        applies a cost based on the type of each node and the route preferences.

        Required implementation of the abstract method in the astar class.

        Args:
            n1 (int): The index of the first waypoint.
            n2 (int): The index of the second waypoint.

        Returns:
            float: The weighted distance between the two nodes.
        """

        # Calculate actual distance
        distance = self.actual_distance_between(n1, n2)

        # Get type of each node
        type1 = self.waypoints[n1][1]
        type2 = self.waypoints[n2][1]

        # The cost associated with the route preferences of the two nodes
        nodes_cost_modifier = (
            self.costs[self.waypoint_preferences[type1]] * self.costs[self.waypoint_preferences[type2]]
        )

        # The cost modifier for distnaces greater than the max_leg_length
        distance_cost_modifier = self.costs['REJECT'] if distance > self.max_leg_length else 1.0

        # If n1 and n2 are adjacent on the same airway, additionally factor in the airway cost modifier
        airway_cost_modifier = 1.0
        if self.airway_preferences:
            for neighbor, aidx in self.connections.get(n1, []):
                if neighbor == n2:
                    # Get the airway type
                    typea = self.airways[aidx][2]
                    airway_cost_modifier = self.costs[self.airway_preferences[typea]]

        # Combine all cost modifiers to get the weighted distance
        return distance * nodes_cost_modifier * distance_cost_modifier * airway_cost_modifier

    def heuristic_cost_estimate(self, current, goal):
        """
        Estimated distance from node current to goal node goal.

        This method calculates the heuristic cost estimate between two waypoints.
        The heuristic cost must always underestimate the actual cost to ensure the
        algorithm finds the least cost path (function is admissible).

        Required implementation of the abstract method in the astar class.

        Args:
            current (int): The index of the first waypoint.
            goal (int): The index of the second waypoint.

        Returns:
            float: The estimated heuristic cost between the two nodes.
        """

        # Calculate actual distance
        distance = self.actual_distance_between(current, goal)

        # Use most favorable possible cost, heuristic_cost_estimate must always underestimate
        cost = self.costs['PREFER'] * self.costs['PREFER']
        return distance * cost


def find_nearest_airport(router: Router, waypoint_idx: int, search_radius_m: float) -> int:
    """Find the nearest airport to a waypoint using the rtree spatial index.

    Args:
        router: Router instance with spatial index and waypoint data
        waypoint_idx: Index of waypoint to search near
        search_radius_m: Search radius in meters

    Returns:
        Waypoint index of the nearest airport, or -1 if none found
    """
    lat, lon = router.waypoints[waypoint_idx][2:4]
    north, east, south, west = bounding_box(lat, lon, search_radius_m)
    candidates = router.waypoints_idx.intersection((west, south, east, north))

    best_idx = -1
    best_dist = float('inf')
    for idx in candidates:
        if router.waypoints[idx][1] in SPLIT_AIRPORT_TYPES:
            dist = haversine(lat, lon, router.waypoints[idx][2], router.waypoints[idx][3])
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

    return best_idx


def route_distance(router: Router, route: list[int]) -> float:
    """Return total route distance in meters by summing haversine between consecutive waypoints."""
    return float(sum(router.actual_distance_between(a, b) for a, b in zip(route, route[1:])))


def find_split_point(
    router: Router,
    route: list[int],
    max_length_m: float,
    via_airport_indices: set[int],
) -> tuple[int, int]:
    """Find a split point airport at or near the route before max_length_m is exceeded.

    Walks route accumulating distance. Prefers via airports when they appear
    within the limit. When no airport exists in the route (e.g. airway routes
    through navaids/fixes), falls back to searching the rtree spatial index
    for the nearest airport near the last route position before the limit.

    Args:
        router: Router instance with waypoint data
        route: List of waypoint indices
        max_length_m: Maximum distance in meters
        via_airport_indices: Set of waypoint indices that are via airports

    Returns:
        Tuple of (route_position, airport_waypoint_index).
        When the airport is in the route: airport_idx == route[route_position].
        When the airport is off-route (nearby fallback): airport_idx != route[route_position].
        Returns (-1, -1) if no airport found anywhere.
    """
    cumulative = 0.0
    last_airport_pos = -1
    last_via_airport_pos = -1
    last_pos_before_limit = 0

    for i in range(1, len(route)):
        cumulative += router.actual_distance_between(route[i - 1], route[i])
        if cumulative > max_length_m:
            break
        last_pos_before_limit = i
        if router.waypoints[route[i]][1] in SPLIT_AIRPORT_TYPES:
            last_airport_pos = i
            if route[i] in via_airport_indices:
                last_via_airport_pos = i

    # Prefer via airport if found
    if last_via_airport_pos > 0:
        return (last_via_airport_pos, route[last_via_airport_pos])
    if last_airport_pos > 0:
        return (last_airport_pos, route[last_airport_pos])

    # Fallback: search for nearest airport near the last position before limit
    if last_pos_before_limit > 0:
        nearby = find_nearest_airport(router, route[last_pos_before_limit], router.max_leg_length)
        if nearby >= 0:
            return (last_pos_before_limit, nearby)

    return (-1, -1)


def compute_route(router: Router, origin: int, destination: int, via_ids: list[int], direct: bool = False) -> list[int]:
    """Compute a route from origin to destination through via waypoints.

    Args:
        router: Router instance for A* pathfinding
        origin: Origin waypoint index
        destination: Destination waypoint index
        via_ids: List of via waypoint indices (order will be optimized)
        direct: If True, skip A* and use direct routing

    Returns:
        List of waypoint indices forming the route
    """
    # Calculate candidate route list (try all permutations of vias)
    candidate_routes = [[origin] + list(perm) + [destination] for perm in itertools.permutations(via_ids)]

    # For each candidate route, calculate the total distance
    routes_and_distances = [
        (cand, sum(router.actual_distance_between(s, e) for s, e in zip(cand, cand[1:]))) for cand in candidate_routes
    ]

    # Pick the shortest direct route
    route, _ = min(routes_and_distances, key=lambda x: x[1])

    # Generate a point-to-point route using A*
    if not direct:
        for start, end in zip(route, route[1:]):
            subroute = router.astar(start, end)
            if subroute:
                route = route[: route.index(start)] + list(subroute) + route[route.index(end) + 1 :]

    return route


def split_route_greedy(
    router: Router,
    route: list[int],
    max_length_m: float,
    via_airport_indices: set[int],
    equal_lengths: bool = False,
) -> list[list[int]]:
    """Split a pre-computed route into flights using greedy strategy.

    Walks the route and splits at airport boundaries when the flight
    length would exceed max_length_m.

    Args:
        router: Router instance with waypoint data
        route: Pre-computed route as list of waypoint indices
        max_length_m: Maximum flight length in meters
        via_airport_indices: Set of waypoint indices that are via airports
        equal_lengths: If True, distribute distance approximately evenly

    Returns:
        List of flights, each a list of waypoint indices
    """
    flights = []
    remaining = route

    if equal_lengths:
        total_dist = route_distance(router, route)
        num_flights = math.ceil(total_dist / max_length_m)
        if num_flights <= 1:
            return [route]
        target_m = total_dist / num_flights
    else:
        num_flights = 0
        target_m = max_length_m

    while len(remaining) > 1:
        rem_dist = route_distance(router, remaining)
        if rem_dist <= target_m:
            # Still split at via airports even when remaining distance fits
            via_pos = next(
                (i for i in range(1, len(remaining) - 1) if remaining[i] in via_airport_indices),
                -1,
            )
            if via_pos > 0:
                flights.append(remaining[: via_pos + 1])
                remaining = remaining[via_pos:]
                continue
            flights.append(remaining)
            break

        split_pos, airport_idx = find_split_point(router, remaining, target_m, via_airport_indices)

        if (split_pos, airport_idx) == (-1, -1):
            # No airport found within limit - warn and include over-length leg
            wp_name = router.waypoints[remaining[0]][0]
            print(
                f"Warning: no airport found within {target_m / 1852:.1f}nm " f"of {wp_name}, including over-length leg",
                file=sys.stderr,
            )
            flights.append(remaining)
            break

        if split_pos == len(remaining) - 1 and airport_idx == remaining[split_pos]:
            # Split point is destination - remaining route fits
            flights.append(remaining)
            break

        if airport_idx == remaining[split_pos]:
            # Airport is in the route (normal case)
            flights.append(remaining[: split_pos + 1])
            remaining = remaining[split_pos:]
        else:
            # Airport is off-route (nearby fallback for airway routes)
            flights.append(remaining[: split_pos + 1] + [airport_idx])
            remaining = [airport_idx] + remaining[split_pos + 1 :]

        if equal_lengths:
            flights_remaining = num_flights - len(flights)
            if flights_remaining > 0:
                target_m = route_distance(router, remaining) / flights_remaining

    return flights


def split_route_recompute(
    router: Router,
    origin: int,
    destination: int,
    via_ids: list[int],
    max_length_m: float,
    via_airport_indices: set[int],
    direct: bool = False,
    equal_lengths: bool = False,
) -> list[list[int]]:
    """Split a route into flights using recompute strategy.

    Re-runs A* from each split point, independently optimizing each leg.

    Args:
        router: Router instance for pathfinding
        origin: Origin waypoint index
        destination: Destination waypoint index
        via_ids: List of via waypoint indices
        max_length_m: Maximum flight length in meters
        via_airport_indices: Set of waypoint indices that are via airports
        direct: If True, use direct routing
        equal_lengths: If True, distribute distance approximately evenly

    Returns:
        List of flights, each a list of waypoint indices
    """
    flights = []
    current_origin = origin
    remaining_vias = list(via_ids)

    if equal_lengths:
        initial_route = compute_route(router, origin, destination, via_ids, direct)
        total_dist = route_distance(router, initial_route)
        num_flights = math.ceil(total_dist / max_length_m)
        if num_flights <= 1:
            return [initial_route]
        target_m = total_dist / num_flights
    else:
        num_flights = 0
        target_m = max_length_m

    while current_origin != destination:
        route = compute_route(router, current_origin, destination, remaining_vias, direct)

        rem_dist = route_distance(router, route)
        if rem_dist <= target_m:
            # Still split at via airports even when remaining distance fits
            via_pos = next(
                (i for i in range(1, len(route) - 1) if route[i] in via_airport_indices),
                -1,
            )
            if via_pos > 0:
                flight = route[: via_pos + 1]
                flights.append(flight)
                current_origin = route[via_pos]
                visited = set(flight)
                remaining_vias = [v for v in remaining_vias if v not in visited]
                continue
            flights.append(route)
            break

        split_pos, airport_idx = find_split_point(router, route, target_m, via_airport_indices)

        if (split_pos, airport_idx) == (-1, -1):
            wp_name = router.waypoints[current_origin][0]
            print(
                f"Warning: no airport found within {target_m / 1852:.1f}nm " f"of {wp_name}, including over-length leg",
                file=sys.stderr,
            )
            flights.append(route)
            break

        if split_pos == len(route) - 1 and airport_idx == route[split_pos]:
            flights.append(route)
            break

        if airport_idx == route[split_pos]:
            # Airport is in the route (normal case)
            flight = route[: split_pos + 1]
            flights.append(flight)
            current_origin = route[split_pos]
        else:
            # Airport is off-route (nearby fallback for airway routes)
            flight = route[: split_pos + 1] + [airport_idx]
            flights.append(flight)
            current_origin = airport_idx

        visited = set(flight)
        remaining_vias = [v for v in remaining_vias if v not in visited]

        if equal_lengths:
            flights_remaining = num_flights - len(flights)
            if flights_remaining > 0:
                next_route = compute_route(router, current_origin, destination, remaining_vias, direct)
                target_m = route_distance(router, next_route) / flights_remaining

    return flights


def split_route_into_flights(
    router: Router,
    route: list[int],
    origin: int,
    destination: int,
    via_ids: list[int],
    max_flight_length_m: float,
    strategy: str,
    equal_lengths: bool = False,
    direct: bool = False,
) -> list[list[int]]:
    """Split a route into multiple flights based on maximum flight length.

    Args:
        router: Router instance
        route: Pre-computed full route
        origin: Origin waypoint index
        destination: Destination waypoint index
        via_ids: List of via waypoint indices
        max_flight_length_m: Maximum flight length in meters
        strategy: Split strategy ('greedy' or 'recompute')
        equal_lengths: If True, distribute distance approximately evenly
        direct: If True, use direct routing for recompute strategy

    Returns:
        List of flights, each a list of waypoint indices.
        Last waypoint of flight N equals first waypoint of flight N+1.
    """
    via_airport_indices = {v for v in via_ids if router.waypoints[v][1] in SPLIT_AIRPORT_TYPES}

    # Check if route fits in a single flight and has no via airports to split at
    has_via_split = any(route[i] in via_airport_indices for i in range(1, len(route) - 1))
    if route_distance(router, route) <= max_flight_length_m and not has_via_split:
        return [route]

    if strategy == SPLIT_STRATEGY_RECOMPUTE:
        return split_route_recompute(
            router, origin, destination, via_ids, max_flight_length_m, via_airport_indices, direct, equal_lengths
        )
    else:
        return split_route_greedy(router, route, max_flight_length_m, via_airport_indices, equal_lengths)


def build_route_text(router: Router, route: list[int], name_fn, minimal_airway: bool = False) -> str:
    """Build textual representation of a route.

    Args:
        router: Router instance with airway data
        route: List of waypoint indices
        name_fn: Function that takes a waypoint index and returns its display name
        minimal_airway: If True, show condensed airway notation

    Returns:
        Route as a text string
    """
    if not minimal_airway:
        return ' '.join(name_fn(idx) for idx in route)

    # Build airway-aware route text
    airway_counts: dict[int, int] = {}
    airway_segments: list[Union[set[int], int, None]] = []
    for wp1, wp2 in zip(route, route[1:]):
        airways_in_segment = set()
        for neighbor, airway in router.connections.get(wp1, []):
            if neighbor == wp2:
                airway_counts[airway] = airway_counts.get(airway, 0) + 1
                airways_in_segment.add(airway)
        airway_segments.append(airways_in_segment)

    current_airway: Optional[int] = None
    for i, segment in enumerate(airway_segments):
        segment_airways: Union[set[int], int, None] = segment
        if not segment_airways:
            current_airway = None
        elif isinstance(segment_airways, set) and current_airway not in segment_airways:
            current_airway = max(segment_airways, key=lambda x: airway_counts[x])
        airway_segments[i] = current_airway

    route_text = ""
    for i, (waypoint_idx, airway_idx) in enumerate(zip(route, airway_segments + [None])):
        if airway_idx is None:
            route_text += name_fn(waypoint_idx) + ' '
        elif i == 0 or (airway_idx != airway_segments[i - 1]):
            route_text += name_fn(waypoint_idx) + ' '
            if airway_idx:
                route_text += f'{router.airways[airway_idx][0]} '
    return route_text.strip()


def main() -> None:
    """
    Main function to generate a flight plan from origin to destination, via an optional list of waypoints.
    """

    # Choices for route preferences
    route_choices = ['PREFER', 'INCLUDE', 'AVOID', 'REJECT']

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Generate a flight plan from origin to destination, via an optional list of waypoints.'
    )

    # Required origin and destination
    parser.add_argument('origin', help='Origin airport code')
    parser.add_argument('destination', help='Destination airport code')

    # Optional via waypoints
    parser.add_argument(
        '--via',
        action='extend',
        nargs='+',
        help='Generated route must include these waypoints (airport, VOR, NDB, VFR waypoint, etc.). Multiple waypoints can be specified in one --via or use --via multiple times. Route planner will determine the shortest route between each via.',
        default=[],
    )

    # Optional user waypoints
    parser.add_argument(
        '--waypoint',
        action='extend',
        nargs='+',
        help='Add user waypoints (format: ID,LAT,LON) that can be used during routing. Multiple waypoints can be specified in one --waypoint or use --waypoint multiple times. User waypoints are treated with PREFER preference by default (configurable with --route-user-waypoint).',
        default=[],
    )

    # Output preferences
    parser.add_argument(
        '--output-minimal-airway',
        action='store_true',
        help='Output a condensed flight plan showing only airway entry and exit waypoints.',
    )
    parser.add_argument(
        '--output-skyvector', action='store_true', help='Open a web browser with the route depicted by Skyvector.'
    )
    parser.add_argument('--output-fpl', type=str, metavar='FILE', help='Output route as a Garmin FPL v1 XML file.')

    # Route generation preferences
    parser.add_argument(
        '--direct',
        action='store_true',
        help='Generate a shortest-path direct flight plan between origin and destination, via any optional vias and exit. No intermediate legs are calculated.',
    )
    parser.add_argument(
        '--airway',
        action='store_true',
        help='Generate a flight plan between origin and destination, via any optional vias, considering airways as well as waypoint-to-waypoint legs.',
    )
    parser.add_argument(
        '--max-leg-length',
        type=float,
        default=DEFAULT_MAX_LEG_LENGTH_NM,
        help='Specify the maximum leg length for direct neighbors, in nautical miles.',
    )

    # Flight splitting options
    parser.add_argument(
        '--max-flight-length',
        type=float,
        default=None,
        metavar='LENGTH',
        help='Split route into multiple flights, each no longer than LENGTH nautical miles. Each flight begins and ends at an airport.',
    )
    parser.add_argument(
        '--equal-flight-lengths',
        action='store_true',
        help='Distribute distance approximately evenly across flights. Requires --max-flight-length.',
    )
    parser.add_argument(
        '--flight-split-strategy',
        choices=[SPLIT_STRATEGY_GREEDY, SPLIT_STRATEGY_RECOMPUTE],
        default=SPLIT_STRATEGY_GREEDY,
        help='Strategy for splitting route into flights. "greedy" splits a single pre-computed route; "recompute" re-runs A* from each split point. Requires --max-flight-length.',
    )

    # Waypoint preferences
    parser.add_argument(
        '--route-airport', choices=route_choices, default='INCLUDE', help='Specify how to handle airports in the route.'
    )
    parser.add_argument(
        '--route-balloonport',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle balloonports in the route.',
    )
    parser.add_argument(
        '--route-seaplane-base',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle seaplane bases in the route.',
    )
    parser.add_argument(
        '--route-gliderport',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle gliderports in the route.',
    )
    parser.add_argument(
        '--route-heliport',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle heliports in the route.',
    )
    parser.add_argument(
        '--route-ultralight',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle ultralight aerodromes in the route.',
    )
    parser.add_argument(
        '--route-user-waypoint',
        choices=route_choices,
        default='PREFER',
        help='Specify how to handle user-defined waypoints in the route.',
    )
    parser.add_argument(
        '--route-vfr-waypoint',
        choices=route_choices,
        default='INCLUDE',
        help='Specify how to handle VFR waypoints in the route.',
    )
    parser.add_argument(
        '--route-dme', choices=route_choices, default='REJECT', help='Specify how to handle DMEs in the route.'
    )
    parser.add_argument(
        '--route-ndb', choices=route_choices, default='REJECT', help='Specify how to handle NDBs in the route.'
    )
    parser.add_argument(
        '--route-ndbdme', choices=route_choices, default='REJECT', help='Specify how to handle NDB/DMEs in the route.'
    )
    parser.add_argument(
        '--route-vor', choices=route_choices, default='REJECT', help='Specify how to handle VORs in the route.'
    )
    parser.add_argument(
        '--route-vortac', choices=route_choices, default='REJECT', help='Specify how to handle VORTACs in the route.'
    )
    parser.add_argument(
        '--route-vordme', choices=route_choices, default='REJECT', help='Specify how to handle VORs in the route.'
    )

    # Airway preferences
    parser.add_argument(
        '--route-airway-victor',
        choices=route_choices,
        default='PREFER',
        help='Specify how to handle Victor airways in the route, if --airway is set.',
    )
    parser.add_argument(
        '--route-airway-rnav',
        choices=route_choices,
        default='INCLUDE',
        help='Specify how to handle RNAV (T and Q) airways in the route, if --airway is set.',
    )
    parser.add_argument(
        '--route-airway-jet',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle Jet airways in the route, if --airway is set.',
    )
    parser.add_argument(
        '--route-airway-color',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle colored airways in the route, if --airway is set.',
    )
    parser.add_argument(
        '--route-airway-other',
        choices=route_choices,
        default='REJECT',
        help='Specify how to handle atlantic, bahama, pacific, and puerto rico airways in the route, if --airway is set.',
    )

    args = parser.parse_args()

    # Exit if origin or destination are not set
    if not args.origin or not args.destination:
        parser.error('You must specify an origin and destination')

    # Validate output FPL path
    if args.output_fpl:
        output_fpl_path = pathlib.Path(args.output_fpl).resolve()
        if not output_fpl_path.parent.exists():
            parser.error(f'Output directory does not exist: {output_fpl_path.parent}')

    # Validate max leg length is positive
    if args.max_leg_length <= 0:
        parser.error(f'Maximum leg length must be positive, got: {args.max_leg_length}')

    # Validate flight splitting arguments
    if args.max_flight_length is not None and args.max_flight_length <= 0:
        parser.error(f'Maximum flight length must be positive, got: {args.max_flight_length}')
    if args.equal_flight_lengths and not args.max_flight_length:
        parser.error('--equal-flight-lengths requires --max-flight-length')
    if args.flight_split_strategy != SPLIT_STRATEGY_GREEDY and not args.max_flight_length:
        parser.error('--flight-split-strategy requires --max-flight-length')

    # Create a mapping from waypoint type to route preference
    waypoint_preferences = {
        # Aerodromes can be configured individually
        'A': args.route_airport,
        'B': args.route_balloonport,
        'C': args.route_seaplane_base,
        'G': args.route_gliderport,
        'H': args.route_heliport,
        'U': args.route_ultralight,
        # User waypoints can be configured
        'USER': args.route_user_waypoint,
        # VFR waypoints can be configured
        'VFR': args.route_vfr_waypoint,
        # These navaids can be configured individually or as a group with --airway
        'DME': 'INCLUDE' if args.airway else args.route_dme,
        'NDB': 'INCLUDE' if args.airway else args.route_ndb,
        'NDB/DME': 'INCLUDE' if args.airway else args.route_ndbdme,
        'VOR': 'INCLUDE' if args.airway else args.route_vor,
        'VORTAC': 'INCLUDE' if args.airway else args.route_vortac,
        'VOR/DME': 'INCLUDE' if args.airway else args.route_vordme,
        # These fixes are only useful for airway routing and can be configured as a group with --airway
        'CN': 'INCLUDE' if args.airway else 'REJECT',
        'MR': 'INCLUDE' if args.airway else 'REJECT',
        'RP': 'INCLUDE' if args.airway else 'REJECT',
        'WP': 'INCLUDE' if args.airway else 'REJECT',
        # These fixes are not useful for routing
        'MW': 'REJECT',
        'NRS': 'REJECT',
        'RADAR': 'REJECT',
        # These navaids are not useful for routing
        'CONSOLAN': 'REJECT',
        'FAN MARKER': 'REJECT',
        'MARINE NDB': 'REJECT',
        'MARINE NDB/DME': 'REJECT',
        'TACAN': 'REJECT',
        'UHF/NDB': 'REJECT',
        'VOT': 'REJECT',
    }

    # Create a mapping from airway designation to route preference
    airway_preferences = {
        'V': args.route_airway_victor,
        'J': args.route_airway_jet,
        'G': args.route_airway_color,
        'A': args.route_airway_color,
        'R': args.route_airway_color,
        'B': args.route_airway_color,
        'RN': args.route_airway_rnav,
        'AT': args.route_airway_other,
        'BF': args.route_airway_other,
        'PA': args.route_airway_other,
        'PR': args.route_airway_other,
    }

    # Calculate maximum leg length in meters
    max_leg_length = args.max_leg_length * 1852

    # Parse user waypoints
    user_waypoints = []
    if args.waypoint:
        for wp_spec in args.waypoint:
            parts = wp_spec.split(',')
            if len(parts) != 3:
                parser.error(f'Invalid waypoint format: {wp_spec}. Expected format: ID,LAT,LON')
            wp_id = parts[0].strip()
            try:
                lat = float(parts[1].strip())
                lon = float(parts[2].strip())
            except ValueError:
                parser.error(f'Invalid coordinates in waypoint: {wp_spec}')

            # Validate coordinate ranges
            if not -90 <= lat <= 90:
                parser.error(f'Latitude must be between -90 and 90, got {lat} in waypoint: {wp_spec}')
            if not -180 <= lon <= 180:
                parser.error(f'Longitude must be between -180 and 180, got {lon} in waypoint: {wp_spec}')

            user_waypoints.append((wp_id, lat, lon))

    # Initialize the router (will raise FileNotFoundError if database doesn't exist)
    try:
        r = Router(waypoint_preferences, airway_preferences if args.airway else None, max_leg_length, user_waypoints)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Find any waypoint by waypoint_id or icao_id
    def find_waypoint(waypoint_id):
        # First try to find non-airport waypoints (favor VOR, NDB, INT, etc.)
        i = next(
            (
                index
                for index, waypoint in enumerate(r.waypoints)
                if (waypoint[0] == waypoint_id or (len(waypoint) > 5 and waypoint[5] == waypoint_id))
                and waypoint[1] not in AIRPORT_TYPES
            ),
            None,
        )

        # If no non-airport waypoint found, search again including airports
        if i is None:
            i = next(
                (
                    index
                    for index, waypoint in enumerate(r.waypoints)
                    if waypoint[0] == waypoint_id or (len(waypoint) > 5 and waypoint[5] == waypoint_id)
                ),
                None,
            )

        if i is None:
            parser.error(f'Waypoint "{waypoint_id}" not found')
        return i

    # Find airport by airport_id or icao_id
    def find_airport(airport_id):
        i = next(
            (
                index
                for index, waypoint in enumerate(r.waypoints)
                if (waypoint[0] == airport_id or (len(waypoint) > 5 and waypoint[5] == airport_id))
                and waypoint[1] in AIRPORT_TYPES
            ),
            None,
        )
        if i is None:
            parser.error(f'Airport "{airport_id}" not found')
        return i

    # Return airport name, preferring icao_id
    def airport_name(airport_index):
        waypoint = r.waypoints[airport_index]
        return waypoint[5] if len(waypoint) > 5 and waypoint[5] else waypoint[0]

    # Get the origin id, and print an error if it does not exist
    origin_id = find_airport(args.origin.upper())

    # Get the destination id, and print an error if it does not exist
    destination_id = find_airport(args.destination.upper())

    # Map waypoint_id to id all vias (supports all waypoint types)
    via_ids = [find_waypoint(via.upper()) for via in args.via]

    # Compute the route
    route = compute_route(r, origin_id, destination_id, via_ids, args.direct)

    # Split route into flights if --max-flight-length specified
    if args.max_flight_length:
        flights = split_route_into_flights(
            r,
            route,
            origin_id,
            destination_id,
            via_ids,
            args.max_flight_length * 1852,
            args.flight_split_strategy,
            args.equal_flight_lengths,
            args.direct,
        )
    else:
        flights = [route]

    multiple_flights = len(flights) > 1
    minimal_airway = args.airway and args.output_minimal_airway

    # Build and print text for each flight
    for flight_num, flight_route in enumerate(flights, 1):
        route_text = build_route_text(r, flight_route, airport_name, minimal_airway)

        if multiple_flights:
            flight_dist_nm = route_distance(r, flight_route) / 1852
            orig_name = airport_name(flight_route[0])
            dest_name = airport_name(flight_route[-1])
            print(f"Flight {flight_num}: {orig_name} to {dest_name} ({flight_dist_nm:.1f}nm)")
            print(f"  {route_text}")
            if args.output_skyvector:
                encoded_route = urllib.parse.quote_plus(route_text)
                print(f"  https://skyvector.com/?fpl={encoded_route}")
            if flight_num < len(flights):
                print()
        else:
            print(route_text)

    # Open the first flight in SkyVector if requested
    if args.output_skyvector:
        first_text = build_route_text(r, flights[0], airport_name, minimal_airway)
        encoded_route = urllib.parse.quote_plus(first_text)
        webbrowser.open(f'https://skyvector.com/?fpl={encoded_route}')
        if multiple_flights:
            print("Note: SkyVector opened with first flight only", file=sys.stderr)

    # Output FPL file(s) if requested
    if args.output_fpl:
        for flight_num, flight_route in enumerate(flights, 1):
            # Determine file path (numbered suffix for multiple flights)
            if multiple_flights:
                fpl_path = output_fpl_path.with_stem(f"{output_fpl_path.stem}_{flight_num}")
            else:
                fpl_path = output_fpl_path

            # Build route list: (identifier, lat, lon, waypoint_type, country_code)
            route_data = []
            for idx in flight_route:
                wp = r.waypoints[idx]
                # wp structure: [id, type, lat, lon, country, icao_id]
                waypoint_id = wp[5] if len(wp) > 5 and wp[5] else wp[0]
                fpl_type = WAYPOINT_TYPE_MAP.get(wp[1], fpl.WAYPOINT_TYPE_USER)
                country = COUNTRY_CODE_MAP.get(wp[4], '')
                route_data.append((waypoint_id, wp[2], wp[3], fpl_type, country))

            # Create route name from flight origin to destination
            orig_name = airport_name(flight_route[0])
            dest_name = airport_name(flight_route[-1])
            route_name = f"{orig_name}/{dest_name}"

            # Create and write flight plan
            flight_plan = fpl.create_flight_plan_from_route_list(route_data, route_name)
            fpl.write_fpl(flight_plan, fpl_path)
            print(f"Flight plan written to {fpl_path}")


if __name__ == '__main__':
    main()
