#!/usr/bin/env python3

import argparse
import astar
import math
import itertools
import pickle
import rtree

def haversine(lat1, lon1, lat2, lon2):
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
    r = 6371000 # Radius of Earth in meters
    return d * r

def bounding_box(lat1, lon1, distance):
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
    r = 6371000 # Radius of Earth in meters
    d = distance / r

    # Shortcut for 45 and 225 degree bearings
    root1_2 = 0.7071067811865476 # sqrt(0.5)

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

class router(astar.AStar):
    def __init__(self, waypoint_preferences, airway_preferences, max_leg_length):
        """
        Initialize all the state needed to implement the a-star pathfinding algorithm.

        Args:
            waypoint_preferences (dict): A dictionary mapping waypoint types to routing preferences.
                                         Possible values are "PREFER", "INCLUDE", "AVOID", and "REJECT".

            max_leg_length (float): The maximum allowable length for any leg of the route.
        """

        # Deserialize waypoints
        with open("waypoints.pickle", "rb") as f:
            self.waypoints = pickle.load(f)

        # Deserialize airways
        with open("airways.pickle", "rb") as f:
            self.airways = pickle.load(f)

        # Deserialize connections
        with open("connections.pickle", "rb") as f:
            self.connections = pickle.load(f)

        # Store the route preferences
        self.waypoint_preferences = waypoint_preferences
        self.airway_preferences = airway_preferences
        self.max_leg_length = max_leg_length

        # Set costs for each route preference
        self.costs = { "PREFER": 0.8, "INCLUDE": 1.0, "AVOID": 1.25, "REJECT": 1000.0 }

        # Construct an rtree index
        def generator_function():
            for id, (_, waypoint_type, lat, lon) in enumerate(self.waypoints):
                if waypoint_preferences[waypoint_type] != 'REJECT':
                    yield (id, (lon, lat, lon, lat), None)
        self.waypoints_idx = rtree.index.Index(generator_function())

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
        _, _, lat1, lon1 = self.waypoints[n1]
        _, _, lat2, lon2 = self.waypoints[n2]

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

        # Construct bounding box around the current waypoint
        _, _, lat, lon = self.waypoints[node]
        north, east, south, west = bounding_box(lat, lon, self.max_leg_length)

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
        nodes_cost_modifier = self.costs[self.waypoint_preferences[type1]] * self.costs[self.waypoint_preferences[type2]]

        # The cost modifier for distnaces greater than the max_leg_length
        distance_cost_modifier = self.costs["REJECT"] if distance > self.max_leg_length else 1.0

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

    def heuristic_cost_estimate(self, n1, n2):
        """
        Estimated distance from node n1 to goal node n2.

        This method calculates the heuristic cost estimate between two waypoints.
        The heuristic cost must always underestimate the actual cost to ensure the
        algorithm finds the least cost path (function is admissible).

        Required implementation of the abstract method in the astar class.

        Args:
            n1 (int): The index of the first waypoint.
            n2 (int): The index of the second waypoint.

        Returns:
            float: The estimated heuristic cost between the two nodes.
        """

        # Calculate actual distance
        distance = self.actual_distance_between(n1, n2)

        # Use most favorable possible cost, heuristic_cost_estimate must always underestimate
        cost = self.costs["PREFER"] * self.costs["PREFER"] * self.costs["PREFER"]
        return distance * cost

def main():
    # Choices for route preferences
    route_choices = ['PREFER', 'INCLUDE', 'AVOID', 'REJECT']

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate a flight plan from origin to destination, via an optional list of waypoints.')

    # Required origin and destination
    parser.add_argument('origin', help='Origin airport code')
    parser.add_argument('destination', help='Destination airport code')

    # Optional via waypoints
    parser.add_argument('--via', action='append', help='Generated route must include this airport, fix, or navaid. Each via must be specified separately, and they can be in any order. Route planner will determine the shortest route between each via.', default=[])

    # Route generation preferences
    parser.add_argument('--direct', action='store_true', help='Generate a shortest-path direct flight plan between origin and destination, via any optional vias and exit. No intermediate legs are calculated.')
    parser.add_argument('--airway', action='store_true', help='Generate a flight plan between origin and destination, via any optional vias, considering airways as well as waypoint-to-waypoint legs.')
    parser.add_argument('--max-leg-length', type=float, default=100, help='Specify the maximum leg length for direct neighbors, in nautical miles.')

    # Waypoint preferences
    parser.add_argument('--route-airport',       choices=route_choices, default='INCLUDE', help='Specify how to handle airports in the route.')
    parser.add_argument('--route-balloonport',   choices=route_choices, default='REJECT',  help='Specify how to handle balloonports in the route.')
    parser.add_argument('--route-seaplane-base', choices=route_choices, default='REJECT',  help='Specify how to handle seaplane bases in the route.')
    parser.add_argument('--route-gliderport',    choices=route_choices, default='REJECT',  help='Specify how to handle gliderports in the route.')
    parser.add_argument('--route-heliport',      choices=route_choices, default='REJECT',  help='Specify how to handle heliports in the route.')
    parser.add_argument('--route-ultralight',    choices=route_choices, default='REJECT',  help='Specify how to handle ultralight aerodromes in the route.')
    parser.add_argument('--route-vfr-waypoint',  choices=route_choices, default='INCLUDE', help='Specify how to handle VFR waypoints in the route.')
    parser.add_argument('--route-dme',           choices=route_choices, default='REJECT',  help='Specify how to handle DMEs in the route.')
    parser.add_argument('--route-ndb',           choices=route_choices, default='REJECT',  help='Specify how to handle NDBs in the route.')
    parser.add_argument('--route-ndbdme',        choices=route_choices, default='REJECT',  help='Specify how to handle NDB/DMEs in the route.')
    parser.add_argument('--route-vor',           choices=route_choices, default='REJECT',  help='Specify how to handle VORs in the route.')
    parser.add_argument('--route-vortac',        choices=route_choices, default='REJECT',  help='Specify how to handle VORTACs in the route.')
    parser.add_argument('--route-vordme',        choices=route_choices, default='REJECT',  help='Specify how to handle VORs in the route.')

    # Airway preferences
    parser.add_argument('--route-airway-victor', choices=route_choices, default='PREFER',  help='Specify how to handle Victor airways in the route.')
    parser.add_argument('--route-airway-rnav',   choices=route_choices, default='INCLUDE', help='Specify how to handle RNAV (T and Q) airways in the route.')
    parser.add_argument('--route-airway-jet',    choices=route_choices, default='REJECT',  help='Specify how to handle Jet airways in the route.')
    parser.add_argument('--route-airway-color',  choices=route_choices, default='REJECT',  help='Specify how to handle colored airways in the route.')
    parser.add_argument('--route-airway-other',  choices=route_choices, default='REJECT',  help='Specify how to handle atlantic, bahama, pacific, and puerto rico airways in the route.')

    args = parser.parse_args()

    # Exit if origin or destination are not set
    if not args.origin or not args.destination:
        parser.error("You must specify an origin and destination")

    # Create a mapping from waypoint type to route preference
    waypoint_preferences = {
        # Aerodromes can be configured individually
        'A': args.route_airport,
        'B': args.route_balloonport,
        'C': args.route_seaplane_base,
        'G': args.route_gliderport,
        'H': args.route_heliport,
        'U': args.route_ultralight,

        # VFR waypoints can be configured
        'VFR': args.route_vfr_waypoint,

        # These navaids can be configured individually or as a group with --airway
        'DME':     "INCLUDE" if args.airway else args.route_dme,
        'NDB':     "INCLUDE" if args.airway else args.route_ndb,
        'NDB/DME': "INCLUDE" if args.airway else args.route_ndbdme,
        'VOR':     "INCLUDE" if args.airway else args.route_vor,
        'VORTAC':  "INCLUDE" if args.airway else args.route_vortac,
        'VOR/DME': "INCLUDE" if args.airway else args.route_vordme,

        # These fixes are only useful for airway routing and can be configured as a group with --airway
        'CN': "INCLUDE" if args.airway else "REJECT",
        'MR': "INCLUDE" if args.airway else "REJECT",
        'RP': "INCLUDE" if args.airway else "REJECT",
        'WP': "INCLUDE" if args.airway else "REJECT",

        # These fixes are not useful for routing
        'MW': "REJECT",
        'NRS': "REJECT",
        'RADAR': "REJECT",

        # These navaids are not useful for routing
        'CONSOLAN': "REJECT",
        'FAN MARKER': "REJECT",
        'MARINE NDB': "REJECT",
        'MARINE NDB/DME': "REJECT",
        'TACAN': "REJECT",
        'UHF/NDB': "REJECT",
        'VOT': "REJECT",
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

    # Initialize the router
    r = router(waypoint_preferences, airway_preferences if args.airway else None, max_leg_length)

    # Get the origin id, and print an error if it does not exist
    origin_id = next((index for index, (waypoint_id, waypoint_type, _, _) in enumerate(r.waypoints) if waypoint_id == args.origin and waypoint_type in ("A", "B", "C", "G", "H", "U")), None)
    if not origin_id:
        parser.error(f"Origin airport '{args.origin}' not found")

    # Get the destination id, and print an error if it does not exist
    destination_id = next((index for index, (waypoint_id, waypoint_type, _, _) in enumerate(r.waypoints) if waypoint_id == args.destination and waypoint_type in ("A", "B", "C", "G", "H", "U")), None)
    if not destination_id:
        parser.error(f"Destination airport '{args.destination}' not found")

    # Map waypoint_id to id all vias
    via_ids = []
    for via in args.via:
        via_id = next((index for index, (waypoint_id, waypoint_type, _, _) in enumerate(r.waypoints) if waypoint_id == via), None)
        if not via_id:
            parser.error(f"Via waypoint '{via}' not found")
        via_ids.append(via_id)

    # Calculate candidate route list
    candidate_routes = [[origin_id] + list(perm) + [destination_id] for perm in itertools.permutations(via_ids)]

    # For each candidate route, calculate the total distance
    routes_and_distances = [(route, sum(r.actual_distance_between(start, end) for start, end in itertools.pairwise(route))) for route in candidate_routes]

    # Pick the shortest direct route
    route, _ = min(routes_and_distances, key=lambda x: x[1])

    # Generate a point-to-point flight plan
    if not args.direct:
        # Find the route between each pair of waypoints
        for start, end in itertools.pairwise(route):
            subroute = r.astar(start, end)
            # Insert the subroute into the main route
            if subroute:
                route = route[:route.index(start)] + list(subroute) + route[route.index(end) + 1:]

    # Output the flight plan
    if route:
        print(" ".join(r.waypoints[id][0] for id in route))
    else:
        print("No route found")

if __name__ == "__main__":
    main()