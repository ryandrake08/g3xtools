#!/usr/bin/env python3

import argparse
import astar
import itertools
import pyproj
import sqlite3

class router(astar.AStar):
    def __init__(self, filename):
        # Store the database connection and cursor
        self.db = sqlite3.connect(filename)
        self.cur = self.db.cursor()

        # Using WGS84
        self.geod = pyproj.Geod(ellps='WGS84')

        # Build an in-memory cache of ids to waypoint data
        self.cur.execute("SELECT id, waypoint_id, lat_decimal, long_decimal FROM waypoints")
        self.waypoints = {id: (waypoint_id, lat, lon) for id, waypoint_id, lat, lon in self.cur.fetchall()}

    def __del__(self):
        self.db.close()

    def neighbors(self, node):
        print(f"neighbors node: {node}")
        self.cur.execute("SELECT id1, id2 FROM neighbors WHERE id1=? OR id2=?", (node, node))
        neighbors = [id2 if id1 == node else id1 for id1, id2 in self.cur.fetchall()]
        return neighbors

    def distance_between(self, n1, n2):
        if n1 == n2:
            return 0
        # Get position of each node from the cache
        _, lat1, lon1 = self.waypoints[n1]
        _, lat2, lon2 = self.waypoints[n2]
        return self.geod.inv(lon1, lat1, lon2, lat2)[2]

    def heuristic_cost_estimate(self, n1, n2):
        return self.distance_between(n1, n2)

    def is_goal_reached(self, current, goal):
        print(f"current: {current}, goal: {goal}")
        return current == goal

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data.')
    parser.add_argument('--db', default='fplan.db', help='Specify the database filename. Uses fpaln.db if not provided.')
    parser.add_argument('--direct', action='store_true', help='Generate a direct flight plan. This is the default if no other route type is specified.')
    parser.add_argument('--p2p', action='store_true', help='Generate a point-to-point flight plan')
    parser.add_argument('--airway', action='store_true', help='Generate a flight plan using airways')
    parser.add_argument('--include-airport', action='store_true', help='Include airports in point-to-point flight plan')
    parser.add_argument('--include-balloonport', action='store_true', help='Include balloonports in point-to-point flight plan')
    parser.add_argument('--include-gliderport', action='store_true', help='Include gliderports in point-to-point flight plan')
    parser.add_argument('--include-heliport', action='store_true', help='Include heliports in point-to-point flight plan')
    parser.add_argument('--include-seaplane-base', action='store_true', help='Include seaplane bases in point-to-point flight plan')
    parser.add_argument('--include-ultralight', action='store_true', help='Include ultralight aerodromes in point-to-point flight plan')
    parser.add_argument('--include-dme', action='store_true', help='Include DMEs in point-to-point flight plan')
    parser.add_argument('--include-ndb', action='store_true', help='Include NDBs, NDB/DMEs, and UHF/NDBs in point-to-point flight plan')
    parser.add_argument('--include-vortac', action='store_true', help='Include VORTACs and TACANs in point-to-point flight plan')
    parser.add_argument('--include-vor', action='store_true', help='Include VORs in point-to-point flight plan')
    parser.add_argument('--include-cns', action='store_true', help='Include CNSs in point-to-point flight plan')
    parser.add_argument('--include-reporting-point', action='store_true', help='Include reporting points in point-to-point flight plan')
    parser.add_argument('--include-vfr-waypoint', action='store_true', help='Include VFR waypoints in point-to-point flight plan')
    parser.add_argument('--include-waypoint', action='store_true', help='Include waypoints in point-to-point flight plan')
    parser.add_argument('--via', action='append', help='Create a route via a specific waypoint', default=[])
    parser.add_argument('origin', help='Origin airport code')
    parser.add_argument('destination', help='Destination airport code')
    args = parser.parse_args()

    # Exit if origin or destination are not set
    if not args.origin or not args.destination:
        parser.error("You must specify an origin and destination")

    # Initialize the router
    r = router(args.db)

    # Map waypoint_id to id for origin, destination, and all vias
    waypoint_ids = [args.origin, args.destination] + args.via
    r.cur.execute('SELECT id, waypoint_id FROM waypoints WHERE waypoint_id IN ({})'.format(','.join('?' for _ in waypoint_ids)), waypoint_ids)
    waypoint_map = {waypoint_id: id for id, waypoint_id in r.cur.fetchall()}

    origin = waypoint_map[args.origin]
    destination = waypoint_map[args.destination]
    vias = [waypoint_map[waypoint_id] for waypoint_id in args.via]

    # Calculate candidate route list
    candidate_routes = [[origin, destination]]
    if vias:
        # Put each permutation of via between origin and destination
        candidate_routes = [[origin] + list(perm) + [destination] for perm in itertools.permutations(vias)]

    # For each candidate route, calculate the total distance
    routes_and_distances = [(route, sum(r.distance_between(start, end) for start, end in itertools.pairwise(route))) for route in candidate_routes]

    # Pick the shortest direct route
    route, _ = min(routes_and_distances, key=lambda x: x[1])

    # Generate a point-to-point flight plan
    if args.p2p:
        # Find the route between each pair of waypoints
        for start, end in itertools.pairwise(route):
            subroute = r.astar(start, end)
            # Insert the subroute into the main route
            if subroute:
                route = route[:route.index(start)] + list(subroute) + route[route.index(end) + 1:]

    # Output the flight plan
    if route:
        waypoint_ids = [r.waypoints[id][0] for id in route]
        print(" ".join(waypoint_ids))
    else:
        print("No route found")

if __name__ == "__main__":
    main()