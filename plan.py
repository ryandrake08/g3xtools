#!/usr/bin/env python3

import argparse
import astar
import itertools
import pyproj
import sqlite3

class router(astar.AStar):
    def __init__(self, waypoints, route_preferences, max_leg_length):
        # Using WGS84
        self.geod = pyproj.Geod(ellps='WGS84')

        # Store the waypoints
        self.waypoints = waypoints

        # Store the route preferences
        self.route_preferences = route_preferences
        self.max_leg_length = max_leg_length

        # Set costs
        self.costs = { "PREFER": 0.8, "INCLUDE": 1.0, "AVOID": 1.25, "REJECT": 1000.0 }

    def __del__(self):
        self.db.close()

    def node_string(self, id):
        return self.waypoints[id][0] + " (" + self.waypoints[id][1] + ")"

    def neighbors(self, node):
        # Construct bounding box around the current waypoint
        _, _, lat, lon = self.waypoints[node]
        (east, north, _) = self.geod.fwd(lon, lat, 45, self.max_leg_length * 1.414213562373095)
        (west, south, _) = self.geod.fwd(lon, lat, 225, self.max_leg_length * 1.414213562373095)

        # Get the neighbors of the current node
        neighbors = [id for id, (_, waypoint_type, lat, lon) in self.waypoints.items() if south <= lat <= north and west <= lon <= east and self.route_preferences[waypoint_type] != 'REJECT']

        return neighbors

    def distance_between(self, n1, n2):
        # Trivial case: same node
        if n1 == n2:
            return 0

        # Get information about each node from the cache
        _, type1, lat1, lon1 = self.waypoints[n1]
        _, type2, lat2, lon2 = self.waypoints[n2]

        # Calculate the distance between the two points
        distance = self.geod.inv(lon1, lat1, lon2, lat2)[2]

        # Calculate total cost
        if distance > self.max_leg_length:
            cost = self.costs["REJECT"]
        else:
            cost = self.costs[self.route_preferences[type1]] * self.costs[self.route_preferences[type2]]

        return distance * cost

    def heuristic_cost_estimate(self, n1, n2):
        # Trivial case: same node
        if n1 == n2:
            return 0

        # Get information about each node from the cache
        _, _, lat1, lon1 = self.waypoints[n1]
        _, _, lat2, lon2 = self.waypoints[n2]

        # Calculate the distance between the two points and adjust based on the cost
        distance = self.geod.inv(lon1, lat1, lon2, lat2)[2]

        # Use most favorable possible cost
        cost = self.costs["PREFER"] * self.costs["PREFER"]

        return distance * cost

    def is_goal_reached(self, current, goal):
        return current == goal

def main():
    # Choices for route preferences
    route_choices = ['PREFER', 'INCLUDE', 'AVOID', 'REJECT']

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data.')
    parser.add_argument('--db', default='fplan.db', help='Specify the database filename. Uses fpaln.db if not provided.')

    parser.add_argument('--route-airport',       choices=route_choices, default='INCLUDE', help='Specify how to handle airports in the route')
    parser.add_argument('--route-balloonport',   choices=route_choices, default='REJECT',  help='Specify how to handle balloonports in the route')
    parser.add_argument('--route-seaplane-base', choices=route_choices, default='REJECT',  help='Specify how to handle seaplane bases in the route')
    parser.add_argument('--route-gliderport',    choices=route_choices, default='REJECT',  help='Specify how to handle gliderports in the route')
    parser.add_argument('--route-heliport',      choices=route_choices, default='REJECT',  help='Specify how to handle heliports in the route')
    parser.add_argument('--route-ultralight',    choices=route_choices, default='REJECT',  help='Specify how to handle ultralight aerodromes in the route')
    parser.add_argument('--route-cns',           choices=route_choices, default='REJECT',  help='Specify how to handle CNSs in the route')
    parser.add_argument('--route-vfr-waypoint',  choices=route_choices, default='INCLUDE', help='Specify how to handle VFR waypoints in the route')
    parser.add_argument('--route-dme',           choices=route_choices, default='REJECT',  help='Specify how to handle DMEs in the route')
    parser.add_argument('--route-ndb',           choices=route_choices, default='REJECT',  help='Specify how to handle NDBs in the route')
    parser.add_argument('--route-ndbdme',        choices=route_choices, default='REJECT',  help='Specify how to handle NDBs in the route')
    parser.add_argument('--route-tacan',         choices=route_choices, default='REJECT',  help='Specify how to handle VORTACs in the route')
    parser.add_argument('--route-uhfndb',        choices=route_choices, default='REJECT',  help='Specify how to handle UHF/NDBs in the route')
    parser.add_argument('--route-vor',           choices=route_choices, default='INCLUDE', help='Specify how to handle VORs in the route')
    parser.add_argument('--route-vortac',        choices=route_choices, default='INCLUDE', help='Specify how to handle VORTACs in the route')
    parser.add_argument('--route-vordme',        choices=route_choices, default='INCLUDE', help='Specify how to handle VORs in the route')

    parser.add_argument('--max-leg-length', type=float, default=100, help='Specify the maximum leg length for direct neighbors, in nautical miles.')

    parser.add_argument('--direct', action='store_true', help='Generate a direct flight plan between origin and destination, via any optional vias')
    parser.add_argument('--via', action='append', help='Generated route must include this waypoint', default=[])
    parser.add_argument('origin', help='Origin airport code')
    parser.add_argument('destination', help='Destination airport code')
    args = parser.parse_args()

    # Exit if origin or destination are not set
    if not args.origin or not args.destination:
        parser.error("You must specify an origin and destination")

    # Create a mapping from waypoint type to route preference
    route_preferences = {
        'A': args.route_airport,
        'B': args.route_balloonport,
        'C': args.route_seaplane_base,
        'G': args.route_gliderport,
        'H': args.route_heliport,
        'U': args.route_ultralight,
        'CN': args.route_cns,
        'MR': "INCLUDE",
        'MW': "REJECT",
        'NRS': "REJECT",
        'RADAR': "REJECT",
        'RP': "INCLUDE",
        'VFR': args.route_vfr_waypoint,
        'WP': "INCLUDE",
        'CONSOLAN': "REJECT",
        'DME': args.route_dme,
        'FAN MARKER': "REJECT",
        'MARINE NDB': "REJECT",
        'MARINE NDB/DME': "REJECT",
        'NDB': args.route_ndb,
        'NDB/DME': args.route_ndbdme,
        'TACAN': args.route_tacan,
        'UHF/NDB': args.route_uhfndb,
        'VOR': args.route_vor,
        'VORTAC': args.route_vortac,
        'VOR/DME': args.route_vordme,
        'VOT': "REJECT"
    }

    # Calculate maximum leg length in meters
    max_leg_length = args.max_leg_length * 1852

    # Ingest waypoints table
    with sqlite3.connect(args.db) as db:
        cur = db.cursor()

        # Build an in-memory cache of ids to waypoint data
        cur.execute("SELECT rowid, waypoint_id, waypoint_type, lat_decimal, long_decimal FROM waypoints")
        waypoints = {id: (waypoint_id, waypoint_type, lat, lon) for id, waypoint_id, waypoint_type, lat, lon in cur.fetchall()}

    # Initialize the router
    r = router(waypoints, route_preferences, max_leg_length)

    # Get the origin id, and print an error if it does not exist
    origin_id = next((id for id, (waypoint_id, waypoint_type, _, _) in r.waypoints.items() if waypoint_id == args.origin and waypoint_type in ("A", "B", "C", "G", "H", "U")), None)
    if not origin_id:
        parser.error(f"Origin airport '{args.origin}' not found")

    # Get the destination id, and print an error if it does not exist
    destination_id = next((id for id, (waypoint_id, waypoint_type, _, _) in r.waypoints.items() if waypoint_id == args.destination and waypoint_type in ("A", "B", "C", "G", "H", "U")), None)
    if not destination_id:
        parser.error(f"Destination airport '{args.destination}' not found")

    # Map waypoint_id to id all vias
    via_ids = []
    for via in args.via:
        via_id = next((id for id, (waypoint_id, waypoint_type, _, _) in r.waypoints.items() if waypoint_id == via and waypoint_type not in ("MR", "RP", "WP")), None)
        if not via_id:
            parser.error(f"Via waypoint '{via}' not found")
        via_ids.append(via_id)

    # Calculate candidate route list
    candidate_routes = [[origin_id] + list(perm) + [destination_id] for perm in itertools.permutations(via_ids)]

    # For each candidate route, calculate the total distance
    routes_and_distances = [(route, sum(r.distance_between(start, end) for start, end in itertools.pairwise(route))) for route in candidate_routes]

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