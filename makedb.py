 #!/usr/bin/env python3

"""
This script processes NASR data and stores it in python data structures which get pickled to disk.

CSV files processed:
    - APT_BASE.csv: Contains airport waypoint data.
    - FIX_BASE.csv: Contains fix waypoint data.
    - NAV_BASE.csv: Contains navigation waypoint data.
    - AWY_BASE.csv: Contains airway data.
    - AWY_SEG_ALT.csv: Contains airway segment data.

Command Line Arguments:
    --current: Downloads the Current data.
    --preview: Downloads the Preview data.
    --name: Downloads archived data by name.
    --list: Lists the available NASR data in the Archive section.
    --filename: Specifies the NASR data filename. Uses basename of URL if not provided.
    --output: Specifies the output database filename. Uses 'nasr.db' if not provided.

Usage:
    python makedb.py --current [--filename <filename>] [--output <output>]
    python makedb.py --preview [--filename <filename>] [--output <output>]
    python makedb.py --list
        (then)
    python makedb.py --name <name> [--filename <filename>] [--output <output>]

        (to skip downloading)
    python makedb.py --filename <filename> [--output <output>]

Raises:
    FileNotFoundError: If no data is found for the specified criteria.
    IndexError: If the CSV data file is not found in the archive.
    urllib.error.HTTPError: If there is an HTTP error during the download process.

Raises:
    FileNotFoundError: If the specified NASR data file is not found.
"""

import argparse
import collections
import csv
import io
import itertools
import nasr
import pickle
import zipfile

# Read CSV file
def read_csv_file(csv_archive, file_name, columns, rowdata):
    with csv_archive.open(file_name) as csv_file:
        csv_wrapper = io.TextIOWrapper(csv_file)
        csv_reader = csv.DictReader(csv_wrapper)
        for row in csv_reader:
            values = [
                # Handling CSV rows: 1. Use ICAO_ID if available, 2. Strip whitespace, 3. Convert to float if necessary
                row['ICAO_ID'].strip() if csv_header == 'ARPT_ID' and row.get('ICAO_ID', None) else
                float(row[csv_header]) if csv_header in ['LAT_DECIMAL', 'LONG_DECIMAL'] else
                row[csv_header].strip()
                    for csv_header in columns]
            rowdata.append(values)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data and store it in data structures useful for flight planning.')
    parser.add_argument('--current', action='store_true', help='Download the Current data.')
    parser.add_argument('--preview', action='store_true', help='Download the Preview data.')
    parser.add_argument('--name', help='Download archived data by name.')
    parser.add_argument('--list', action='store_true', help='List of NASR data in the Archive section.')
    parser.add_argument('--filename', help='Specify the NASR data filename. Uses basename of URL if not provided.')
    parser.add_argument('--output', default='nasr.db', help='Specify the output database filename.')
    args = parser.parse_args()

    # Process the archive section
    if args.list:
        # List available NASR data if --list is passed, then exit
        print('\n'.join(nasr.list_archives().keys()))
        return

    elif args.name:
        # Look up fullzip link by name
        fullzip_link = nasr.list_archives().get(args.name)

        # Download the file
        filename = nasr.download(fullzip_link, args.filename)

    elif args.preview or args.current:
        # Process the Preview or Current section
        fullzip_link = list(nasr.current_or_preview('Preview' if args.preview else 'Current').values())[0]

        # Download the file
        filename = nasr.download(fullzip_link, args.filename)

    elif args.filename:
        filename = args.filename

    else:
        raise FileNotFoundError('nasr: No data found or specified.')  

    waypoints = []
    airways = []
    airway_seg = []

    # Open archive
    with zipfile.ZipFile(filename) as archive:
        # Find the CSV data file the archive
        csv_data_name = [name for name in archive.namelist() if name.startswith('CSV_Data/') and name.endswith('.zip')][0]

        # Open the single file inside the CSV_Data folder as a new ZipFile
        with archive.open(csv_data_name) as csv_data_file:
            # Treat the file as a ZipFile
            with zipfile.ZipFile(csv_data_file) as csv_archive:
                # Read waypoint data
                read_csv_file(csv_archive, 'APT_BASE.csv', ['ARPT_ID', 'SITE_TYPE_CODE', 'LAT_DECIMAL', 'LONG_DECIMAL', 'COUNTRY_CODE'], waypoints)
                read_csv_file(csv_archive, 'FIX_BASE.csv', ['FIX_ID', 'FIX_USE_CODE', 'LAT_DECIMAL', 'LONG_DECIMAL', 'COUNTRY_CODE'], waypoints)
                read_csv_file(csv_archive, 'NAV_BASE.csv', ['NAV_ID', 'NAV_TYPE', 'LAT_DECIMAL', 'LONG_DECIMAL', 'COUNTRY_CODE'], waypoints)

                # Read airway data
                read_csv_file(csv_archive, 'AWY_BASE.csv', ['AWY_ID', 'AWY_LOCATION', 'AWY_DESIGNATION'], airways)
                read_csv_file(csv_archive, 'AWY_SEG_ALT.csv', ['AWY_ID', 'AWY_LOCATION', 'FROM_POINT', 'FROM_PT_TYPE', 'TO_POINT', 'COUNTRY_CODE', 'AWY_SEG_GAP_FLAG'], airway_seg)

    # Build a temporary reverse lookup dictionary of waypoint_id to [list of waypoint index]
    # Unfortunately waypoint_id are not unique
    waypoint_lookup = collections.defaultdict(list)
    for i, waypoint in enumerate(waypoints):
        waypoint_lookup[waypoint[0]].append(i)

    # Build a temporary dictionary of (airway_id, airway_location) to airway_index
    # Also, airway_id are not unique, but (airway_id, airway_location) are
    airway_lookup = {(row[0], row[1]): i for i, row in enumerate(airways)}

    # Build a temporary list of airway_index, [list of waypoint index]
    # An airway_index can be associated with multiple lists of waypoints if the airway has gaps
    airway_lists = []
    current_waypoint_index_list = []
    for airway_id, airway_location, from_point, from_point_type, to_point, country_code, gap in airway_seg:
        # Look up airway index
        airway_index = airway_lookup[airway_id, airway_location]

        # Look up the waypoint indices from our temporary reverse lookup dictionary
        waypoint_indices = waypoint_lookup.get(from_point, [])

        # Find the waypoint index that matches the type and country code
        matching_waypoint_indices = [i for i in waypoint_indices if waypoints[i][1] == from_point_type and waypoints[i][4] == country_code]

        assert len(matching_waypoint_indices) <= 1, f'Warning: Waypoint {from_point} has indices: {waypoint_indices}'
        if matching_waypoint_indices:
            # Add the waypoint index to the current waypoint index list
            current_waypoint_index_list.append(matching_waypoint_indices[0])

        # If there is a gap, or if we are at the end of the airway, start a new list
        if gap == 'Y' or not to_point:
            airway_lists.append((airway_index, current_waypoint_index_list))
            current_waypoint_index_list = []

    # Go through each list pairwise and build a dictionary of airway connections: waypoint_index to (neighbor waypoint_index, airway_index)
    connections = collections.defaultdict(list)
    for airway_index, waypoint_indices in airway_lists:
        for i1, i2 in itertools.pairwise(waypoint_indices):
            connections[i1].append((i2, airway_index))
            connections[i2].append((i1, airway_index))

    # Serialize waypoints
    with open('waypoints.pickle', 'wb') as f:
        pickle.dump(waypoints, f)

    # Serialize airway base
    with open('airways.pickle', 'wb') as f:
        pickle.dump(airways, f)

    # Serialize connections
    with open('connections.pickle', 'wb') as f:
        pickle.dump(connections, f)

if __name__ == '__main__':
    main()