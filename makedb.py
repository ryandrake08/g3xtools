 #!/usr/bin/env python3

"""
This script processes NASR data and stores it in lists which get pickled to disk.

CSV files processed:
    - APT_BASE.csv: Contains airport waypoint data.
    - FIX_BASE.csv: Contains fix waypoint data.
    - NAV_BASE.csv: Contains navigation waypoint data.
    - AWY_BASE.csv: Contains airway data.

Command line arguments:
    --filename: Specify the NASR data filename.

Usage:
    python makedb.py --filename <filename>

Raises:
    FileNotFoundError: If the specified NASR data file is not found.
    IndexError: If the CSV data file is not found in the archive.
"""

import argparse
import collections
import csv
import io
import itertools
import pickle
import zipfile

# Read CSV file
def read_csv_file(csv_archive, file_name, columns, rowdata):
    with csv_archive.open(file_name) as csv_file:
        csv_wrapper = io.TextIOWrapper(csv_file)
        csv_reader = csv.DictReader(csv_wrapper)
        for row in csv_reader:
            values = [row['ICAO_ID'].strip() if csv_header == 'ARPT_ID' and 'ICAO_ID' in row and row['ICAO_ID'] else float(row[csv_header]) if csv_header in ['LAT_DECIMAL', 'LONG_DECIMAL'] else row[csv_header].strip() for csv_header in columns]
            rowdata.append(tuple(values))

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process NASR data and store it in data structures useful for flight planning.')
    parser.add_argument('--filename', required=True, help='Specify the NASR data filename.')
    args = parser.parse_args()

    waypoints = []
    airways = []

    # Open archive
    with zipfile.ZipFile(args.filename) as archive:
        # Find the CSV data file the archive
        csv_data_name = [name for name in archive.namelist() if name.startswith('CSV_Data/') and name.endswith('.zip')][0]

        # Open the single file inside the CSV_Data folder as a new ZipFile
        with archive.open(csv_data_name) as csv_data_file:
            # Treat the file as a ZipFile
            with zipfile.ZipFile(csv_data_file) as csv_archive:
                # Read waypoint data
                read_csv_file(csv_archive, 'APT_BASE.csv', ['ARPT_ID', 'SITE_TYPE_CODE', 'LAT_DECIMAL', 'LONG_DECIMAL'], waypoints)
                read_csv_file(csv_archive, 'FIX_BASE.csv', ['FIX_ID', 'FIX_USE_CODE', 'LAT_DECIMAL', 'LONG_DECIMAL'], waypoints)
                read_csv_file(csv_archive, 'NAV_BASE.csv', ['NAV_ID', 'NAV_TYPE', 'LAT_DECIMAL', 'LONG_DECIMAL'], waypoints)

                # Read airway data
                read_csv_file(csv_archive, 'AWY_SEG_ALT.csv', ['AWY_ID', 'AWY_LOCATION', 'FROM_POINT', 'FROM_PT_TYPE'], airways)

    # Build a temporary lookup dictionary of waypoint_id to waypoint_index
    waypoint_lookup = {}
    for i, waypoint in enumerate(waypoints):
        ei = waypoint_lookup.get(waypoint[0], None)
        if isinstance(ei, list):
            ei.append(i)
        elif ei:
            waypoint_lookup[waypoint[0]] = [ei, i]
        else:
            waypoint_lookup[waypoint[0]] = i

    # Build a temporary dictionary of airway connections, keyed by (airway_id, airway_location)
    airway_lists = collections.defaultdict(list)
    for row in airways:
        airway_id, airway_location, point, waypoint_type = row

        # Look up the waypoint index from our temporary lookup dictionary
        waypoint_index = waypoint_lookup.get(point)

        # If the waypoint is not found, skip it. AWY_SEG_ALT.csv contains pseudo-waypoints for the US border that we don't use
        if waypoint_index is None:
            continue

        # If there are multiple waypoints with the same ID, decide which one to use
        if isinstance(waypoint_index, list):
            # Find the first waypoint that matches the type
            for i in waypoint_index:
                if waypoints[i][1] == waypoint_type:
                    waypoint_index = i
                    break
            # If we didn't find a match, raise an error
            if isinstance(waypoint_index, list):
                raise ValueError(f"No waypoints in {waypoint_index} matches the type {waypoint_type}")

        # Add the waypoint index to the airway list
        airway_lists[(airway_id, airway_location)].append(waypoint_index)

    # Build a dictionary of airway connections: waypoint_index to (neighbor_index, airway_id, airway_location)
    connections = collections.defaultdict(list)
    for (airway_id, airway_location), waypoint_indices in airway_lists.items():
        for i1, i2 in zip(waypoint_indices, waypoint_indices[1:]):
            connections[i1].append((i2, airway_id, airway_location))
            connections[i2].append((i1, airway_id, airway_location))

    # Serialize waypoints
    with open('waypoints.pickle', 'wb') as f:
        pickle.dump(waypoints, f)

    # Serialize connections
    with open('connections.pickle', 'wb') as f:
        pickle.dump(connections, f)

if __name__ == '__main__':
    main()