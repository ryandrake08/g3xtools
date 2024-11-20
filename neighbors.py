#!/usr/bin/env python3

"""
This script processes waypoints and airways from a SQLite database to determine direct neighbors
based on a maximum leg length and inserts the results into a neighbors table.

Command Line Arguments:
    --db: Specify the database filename. Uses 'fplan.db' if not provided.
    --max-leg-length: Specify the maximum leg length for direct neighbors, in nautical miles. Default is 100.

Usage:
    python neighbors.py
    python neighbors.py --db <database>
    python neighbors.py --db <database> --max-leg-length <length>

Raises:
    sqlite3.Error: If there is an error with the SQLite database.
"""

import argparse
import pyproj
import sqlite3
import itertools

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data.')
    parser.add_argument('--db', default='fplan.db', help='Specify the database filename. Uses fpaln.db if not provided.')
    parser.add_argument('--max-leg-length', type=float, default=100, help='Specify the maximum leg length for direct neighbors, in nautical miles.')
    args = parser.parse_args()

    # Calculate maximum leg length in meters
    max_leg_length = args.max_leg_length * 1852

    # Using WGS84
    geod = pyproj.Geod(ellps='WGS84')

    # Open SQLITE3 database
    with sqlite3.connect(args.db) as db:
        cur = db.cursor()

        # Drop the neighbors table if it exists
        cur.execute('DROP TABLE IF EXISTS neighbors')

        # Create the neighbors table if it does not exist
        cur.execute('CREATE TABLE neighbors (id1 INTEGER NOT NULL, id2 INTEGER NOT NULL, type INTEGER)')

        # Fetch all direct-routeable waypoints
        cur.execute('SELECT id, lat_decimal, long_decimal FROM waypoints WHERE waypoint_type NOT IN ("MR", "RP", "WP")')
        waypoints = cur.fetchall()

        # Generate dictionary of bounding boxes
        bounding_boxes = {}
        for id, lat, lon in waypoints:
            # Construct bounding box around the current waypoint
            (east, north, _) = geod.fwd(lon, lat, 45, max_leg_length * 1.414213562373095)
            (west, south, _) = geod.fwd(lon, lat, 225, max_leg_length * 1.414213562373095)
            bounding_boxes[id] = (south, north, west, east)

        # Calculate distances and insert into ways table
        neighbors_to_insert = []
        for (id, lat, lon), (nid, neighbor_lat, neighbor_lon) in itertools.combinations(waypoints, 2):
            # Bounding box around current waypoint
            (south, north, west, east) = bounding_boxes[id]

            # Find neighbors within the bounding box
            if south <= neighbor_lat <= north and west <= neighbor_lon <= east:
                neighbors_to_insert.append((id, nid, None))

        # Insert into neighbors table
        if neighbors_to_insert:
            cur.executemany('INSERT INTO neighbors (id1, id2, type) VALUES (?, ?, ?)', neighbors_to_insert)

        # Commit changes
        db.commit()

        # Fetch all waypoints
        cur.execute('SELECT id, waypoint_id FROM waypoints')
        waypoint_id_to_id = {waypoint_id: id for id, waypoint_id in cur.fetchall()}

        # Fetch all airways
        cur.execute('SELECT id, airway_string FROM airways')
        airways = cur.fetchall()

        # For each airway
        for aid, airway_string in airways:
            # Build the list of row ids from waypoint ids while preserving order
            wids = [waypoint_id_to_id[waypoint_id] for waypoint_id in airway_string.split()]

            # Insert each neighbor pairwise
            neighbors_to_insert = [(wid1, wid2, aid) for wid1, wid2 in itertools.pairwise(wids)]

            # Insert into neighbors table
            cur.executemany('INSERT INTO neighbors (id1, id2, type) VALUES (?, ?, ?)', neighbors_to_insert)

        # Commit changes
        db.commit()

if __name__ == '__main__':
    main()