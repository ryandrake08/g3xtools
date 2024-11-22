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
                read_csv_file(csv_archive, 'AWY_BASE.csv', ['AWY_ID', 'AWY_LOCATION', 'AWY_DESIGNATION', 'AIRWAY_STRING'], airways)

    # Data cleaning: Special cases
    def decide_between(i1, i2):
        waypoint1 = waypoints[i1]
        waypoint2 = waypoints[i2]

        # Prefer VOR/DME or VORTAC, or TACAN and dis-prefer VOT, FAN MARKER, or MARINE NDB
        if waypoint1[1] in ['VOR/DME', 'VORTAC', 'TACAN', 'DME'] or waypoint2[1] in ["VOT", "FAN MARKER", "MARINE NDB"]:
            return i1
        if waypoint2[1] in ['VOR/DME', 'VORTAC', 'TACAN', "DME" ] or waypoint1[1] in ["VOT", "FAN MARKER", "MARINE NDB"]:
            return i2

        # If both are named "AP", prefer the one whose longitude < -100. We know this one is part of airway A16
        if waypoint1[0] == 'AP' and waypoint1[3] < -100:
            return i1
        if waypoint2[0] == 'AP' and waypoint2[3] < -100:
            return i2

        # The rest are two-letter NDBs that (as of the time this code was written) are not part of any airway
        return i1

    # Build a temporary lookup dictionary of waypoint_id to waypoint_index
    waypoint_lookup = {}
    for i, waypoint in enumerate(waypoints):
        ei = waypoint_lookup.get(waypoint[0], None)
        if ei:
            waypoint_lookup[waypoint[0]] = decide_between(ei, i)
        else:
            waypoint_lookup[waypoint[0]] = i

    # Build a dictionary of airway connections: waypoint_index to [(neighbor_index, airway_index)]
    connections = collections.defaultdict(list)
    for i, airway in enumerate(airways):
        # Get the list of waypoints in the airway
        waypoint_indices = [waypoint_lookup[waypoint_id] for waypoint_id in airway[3].split(' ')]

        # For each pair of waypoints in the airway, add a connection in both directions
        for waypoint_index, neighbor_index in itertools.pairwise(waypoint_indices):
            connections[waypoint_index].append((neighbor_index, i))
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