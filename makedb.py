 #!/usr/bin/env python3

"""
This script processes NASR data and stores it in an SQLite database. It also builds a neighbors table
to track connections between waypoints.

Database tables:
    - waypoints: Stores waypoint data with columns for waypoint ID, type, latitude, and longitude.
    - airways: Stores airway data with columns for airway ID, location, designation, and airway string.
    - neighbors: Stores connections between waypoints with columns for two waypoint IDs and a type.

CSV files processed:
    - APT_BASE.csv: Contains airport waypoint data.
    - FIX_BASE.csv: Contains fix waypoint data.
    - NAV_BASE.csv: Contains navigation waypoint data.
    - AWY_BASE.csv: Contains airway data.

Command line arguments:
    --filename: Specify the NASR data filename.
    --db: Specify the database filename. Uses 'fplan.db' if not provided.
    --max-leg-length: Specify the maximum leg length for direct neighbors, in nautical miles. Default is 100.
                      Note: This value largely drives the size of the database and the performance of flight planning.

Usage:
    python makedb.py --filename <filename>
    python makedb.py --filename <filename> --db <database>
    python makedb.py --filename <filename> --max-leg-length <length>

Raises:
    FileNotFoundError: If the specified NASR data file is not found.
    sqlite3.Error: If there is an error with the SQLite database.
"""

import argparse
import csv
import io
import os
import pyproj
import sqlite3
import itertools
import zipfile

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data.')
    parser.add_argument('--filename', help='Specify the NASR data filename.')
    parser.add_argument('--db', default='fplan.db', help='Specify the database filename. Uses fpaln.db if not provided.')
    parser.add_argument('--max-leg-length', type=float, default=100, help='Specify the maximum leg length for direct neighbors, in nautical miles.')
    args = parser.parse_args()

    # Set filename
    filename = args.filename if args.filename else None

    # Calculate maximum leg length in meters
    max_leg_length = args.max_leg_length * 1852

    # Delete old db file if it exists
    os.remove(args.db) if os.path.exists(args.db) else None

    # Open new SQLITE3 database
    with sqlite3.connect(args.db) as db:
        cur = db.cursor()

        # waypoint_type:

        # [-] means type is not included in database
        # [/] means type is not direct-routeable

        #     A = Airport
        #     B = Balloonport
        #     C = Seaplane Base
        #     G = Gliderport
        #     H = Heliport
        #     U = Ultralight

        #     CN = Computer Navigation Fix
        # [/] MR = Military Reporting Point
        # [-] MW = Military Waypoint
        # [-] NRS = NRS Waypoint
        # [-] RADAR = Radar
        # [/] RP = Reporting Point
        #     VFR = VFR Waypoint
        # [/] WP = Waypoint

        # [-] CONSOLAN = A Low Frequency, Long-Distance NAVAID Used Principally for Transoceanic navigation.
        #     DME = Distance Measuring Equipment only.
        # [-] FAN MARKER = There are 3 types of EN ROUTE Market Beacons. FAN MARKER, Low powered FAN MARKERS and Z MARKERS. A FAN MARKER Is used to provide a positive identification of positions at Definite points along the airways.
        # [-] MARINE NDB = A NON Directional Beacon used primarily for Marine (surface) Navigation.
        # [-] MARINE NDB/DME = A NON Directional Beacon with associated Distance measuring Equipment; used primarily for Marine (surface) Navigation.
        #     NDB = A NON Directional Beacon
        #     NDB/DME = Non Directional Beacon with associated Distance Measuring Equipment.
        #     TACAN = A Tactical Air Navigation System providing Azimuth and Slant Range Distance.
        #     UHF/NDB = Ultra High Frequency/NON Directional Beacon.
        #     VOR = A VHF OMNI-Directional Range providing Azimuth only.
        #     VORTAC = A Facility consisting of two components, VOR and TACAN, Which provides three individual services: VOR AZIMITH, TACAN AZIMUTH and TACAN Distance (DME) at one site.
        #     VOR/DME = VHF OMNI-DIRECTIONAL Range with associated Distance Measuring equipment.
        # [-] VOT = A FAA VOR Test Facility.

        # Create waypoint table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS waypoints (
                waypoint_id TEXT NOT NULL,
                waypoint_type TEXT NOT NULL,
                lat_decimal REAL NOT NULL,
                long_decimal REAL NOT NULL
            )
        ''')

        # airway_location:

        #     A = Alaska
        #     C = Contiguous U.S.
        #     H = Hawaii

        # airway_designation:

        #     A = Amber colored airway
        #     AT = Atlantic airway
        #     B = Blue colored airway
        #     BF = Bahama airway
        #     G = Green colored airway
        #     J = Jet airway
        #     PA = Pacific airway
        #     PR = Puerto Rico airway
        #     R = Red colored airway
        #     RN = RNAV airway (tango and quebec airways)
        #     V = Victor airway

        # Create airway table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS airways (
                airway_id TEXT NOT NULL,
                airway_location TEXT NOT NULL,
                airway_designation TEXT NOT NULL,
                airway_string TEXT NOT NULL
            )
        ''')

        # Open archive
        with zipfile.ZipFile(filename) as archive:
            # Find the CSV data file the archive
            csv_data_name = [name for name in archive.namelist() if name.startswith('CSV_Data/') and name.endswith('.zip')][0]

            # Open the single file inside the CSV_Data folder as a new ZipFile
            with archive.open(csv_data_name) as csv_data_file:
                # Treat the file as a ZipFile
                with zipfile.ZipFile(csv_data_file) as csv_archive:

                    # Process each CSV file
                    def process_csv_file(csv_archive, file_name, table_name, columns):
                        with csv_archive.open(file_name) as csv_file:
                            csv_wrapper = io.TextIOWrapper(csv_file)
                            csv_reader = csv.DictReader(csv_wrapper)

                            for row in csv_reader:
                                values = []
                                for csv_header, col in columns:
                                    if csv_header == 'ARPT_ID' and 'ICAO_ID' in row and row['ICAO_ID']:
                                        values.append(row['ICAO_ID'].strip())
                                    elif col in ['lat_decimal', 'long_decimal']:
                                        values.append(float(row[csv_header]))
                                    else:
                                        values.append(row[csv_header].strip())
                                values = tuple(values)
                                cur.execute(f'INSERT INTO {table_name} ({', '.join(col for _, col in columns)}) VALUES ({', '.join(['?' for _ in columns])})', values)

                    # Define the files and their corresponding table and columns
                    files_to_process = [
                        ('APT_BASE.csv', 'waypoints', [('ARPT_ID', 'waypoint_id'), ('SITE_TYPE_CODE', 'waypoint_type'), ('LAT_DECIMAL', 'lat_decimal'), ('LONG_DECIMAL', 'long_decimal')]),
                        ('FIX_BASE.csv', 'waypoints', [('FIX_ID', 'waypoint_id'), ('FIX_USE_CODE', 'waypoint_type'), ('LAT_DECIMAL', 'lat_decimal'), ('LONG_DECIMAL', 'long_decimal')]),
                        ('NAV_BASE.csv', 'waypoints', [('NAV_ID', 'waypoint_id'), ('NAV_TYPE', 'waypoint_type'), ('LAT_DECIMAL', 'lat_decimal'), ('LONG_DECIMAL', 'long_decimal')]),
                        ('AWY_BASE.csv', 'airways',   [('AWY_ID', 'airway_id'), ('AWY_LOCATION', 'airway_location'), ('AWY_DESIGNATION', 'airway_designation'), ('AIRWAY_STRING', 'airway_string')])
                    ]

                    # Process each file
                    for file_name, table_name, columns in files_to_process:
                        process_csv_file(csv_archive, file_name, table_name, columns)

        # Using WGS84
        geod = pyproj.Geod(ellps='WGS84')

        # Delete unneeded waypoint_types
        cur.execute('DELETE FROM waypoints WHERE waypoint_type IN ("MW", "NRS", "RADAR", "CONSOLAN", "FAN MARKER", "MARINE NDB", "MARINE NDB/DME", "VOT")')

        # Create the neighbors table if it does not exist
        cur.execute('CREATE TABLE neighbors (id1 INTEGER NOT NULL, id2 INTEGER NOT NULL, type INTEGER)')

        # Fetch all direct-routeable waypoints
        cur.execute('SELECT rowid, lat_decimal, long_decimal FROM waypoints WHERE waypoint_type NOT IN ("MR", "RP", "WP")')
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

        # Fetch all waypoints
        cur.execute('SELECT rowid, waypoint_id FROM waypoints')
        waypoint_id_to_id = {waypoint_id: id for id, waypoint_id in cur.fetchall()}

        # Fetch all airways
        cur.execute('SELECT rowid, airway_string FROM airways')
        airways = cur.fetchall()

        # For each airway
        for aid, airway_string in airways:
            # Build the list of row ids from waypoint ids while preserving order
            wids = [waypoint_id_to_id[waypoint_id] for waypoint_id in airway_string.split()]

            # Insert each neighbor pairwise
            neighbors_to_insert = [(wid1, wid2, aid) for wid1, wid2 in itertools.pairwise(wids)]

            # Insert into neighbors table
            cur.executemany('INSERT INTO neighbors (id1, id2, type) VALUES (?, ?, ?)', neighbors_to_insert)

if __name__ == '__main__':
    main()