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
                read_csv_file(csv_archive, 'AWY_BASE.csv', ['AWY_ID', 'AWY_LOCATION', 'AWY_DESIGNATION', 'AIRWAY_STRING'], airways)

    # Build a lookup table of waypoint_id to waypoint_index
    waypoint_lookup = {waypoint[0]: i for i, waypoint in enumerate(waypoints)}

    # Build a dictionary of airway connections: waypoint_index -> [(neighbor_index, airway_index)]
    connections = {}
    for i, airway in enumerate(airways):
        airway_string = airway[3]
        airway_waypoints = airway_string.split(' ')
        waypoint_indices = [waypoint_lookup.get(wp) for wp in airway_waypoints]

        # For each pair of waypoints in the airway, add a connection in both directions
        for waypoint_index, neighbor_index in itertools.pairwise(waypoint_indices):
            if waypoint_index not in connections:
                connections[waypoint_index] = []
            connections[waypoint_index].append((neighbor_index, i))
            if neighbor_index not in connections:
                connections[neighbor_index] = []
            connections[neighbor_index].append((waypoint_index, i))

    # Serialize waypoints
    with open('waypoints.pickle', 'wb') as f:
        pickle.dump(waypoints, f)

    # Serialize airways
    with open('airways.pickle', 'wb') as f:
        pickle.dump(airways, f)

    # Serialize connections
    with open('connections.pickle', 'wb') as f:
        pickle.dump(connections, f)

if __name__ == '__main__':
    main()