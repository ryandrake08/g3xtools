 #!/usr/bin/env python3

"""
This script processes NASR data and stores it in python data structures which get pickled to disk.

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
                read_csv_file(csv_archive, 'AWY_SEG_ALT.csv', ['AWY_ID', 'AWY_LOCATION', 'FROM_POINT', 'FROM_PT_TYPE', 'TO_POINT', 'AWY_SEG_GAP_FLAG'], airways)

    # Build a temporary reverse lookup dictionary of waypoint_id to waypoint_indices
    waypoint_lookup = collections.defaultdict(list)
    for i, waypoint in enumerate(waypoints):
        waypoint_lookup[waypoint[0]].append(i)

    # Build a temporary list of airway_id, airway_location, (waypoint index lists)
    airway_lists = []
    current_waypoint_index_list = []
    for row in airways:
        airway_id, airway_location, from_point, from_point_type, to_point, gap = row

        # Look up the waypoint index from our temporary reverse lookup dictionary
        waypoint_indices = waypoint_lookup.get(from_point)
        if waypoint_indices:
            # Find the waypoint index that matches the type
            matching_waypoint_indices = [i for i in waypoint_indices if waypoints[i][1] == from_point_type]

            # Special case: Disregard ALPENA, which is an NDB and has id AP but is not part of an airway
            if from_point == 'AP' and from_point_type == 'NDB':
                matching_waypoint_indices = [i for i in matching_waypoint_indices if waypoints[i][3] <= -100]

            # Ensure there is exactly one matching waypoint index
            if len(matching_waypoint_indices) == 0:
                raise ValueError(f'While examining airway {airway_id}, no waypoints with id {from_point} and type {from_point_type} found')
            elif len(matching_waypoint_indices) > 1:
                raise ValueError(f'While examining airway {airway_id}, multiple waypoints with id {from_point} and type {from_point_type} found')

            # Add the waypoint index to the current waypoint index list
            current_waypoint_index_list.append(matching_waypoint_indices[0])

        # If there is a gap, or if we are at the end of the airway, start a new list
        if gap == 'Y' or not to_point:
            airway_lists.append((airway_id, airway_location, current_waypoint_index_list))
            current_waypoint_index_list = []

    # Go through each list pairwise and build a dictionary of airway connections: waypoint_index to (neighbor_index, airway_id, airway_location)
    connections = collections.defaultdict(list)
    for airway_id, airway_location, waypoint_indices in airway_lists:
        for i1, i2 in itertools.pairwise(waypoint_indices):
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