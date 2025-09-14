#!/usr/bin/env python3

import argparse
import glob
import os
import pandas
import re
import shutil
import sys

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process and categorize Garmin G3X aircraft data logs')
    parser.add_argument('search_path', nargs='?', help='Path to search for data_log directories')
    parser.add_argument('-o', '--output', help='Output directory for processed logs')
    parser.add_argument('-v', '--verbose', action='store_true', help='Output metadata information for each log file')
    args = parser.parse_args()

    # Determine search path: command line > environment > error
    mount_root = args.search_path or os.getenv('G3X_SEARCH_PATH')
    if not mount_root:
        print("Error: Search path must be provided via G3X_SEARCH_PATH environment variable or command line argument", file=sys.stderr)
        sys.exit(1)

    # Search recursively for G3X log files (log_*.csv)
    src_logs = sorted(glob.glob(f"{mount_root}/**/log_*.csv", recursive=True))

    # Determine output path: command line > environment. If not specified, no files are output
    log_path = args.output or os.getenv('G3X_LOG_PATH')

    # Create destination subfolders
    if log_path:
        [os.makedirs(os.path.join(log_path, subdir), exist_ok=True) for subdir in ["config", "flight", "taxi"]]

    # Process each log source
    for log in src_logs:

        # Read first line in file (metadata)
        with open(log, "r") as file:
            first_line = file.readline()

        # Comma separated
        metadata_text = first_line.strip().split(",")

        # Verify first item
        if metadata_text[0] != "#airframe_info":
            raise ValueError("Not a Garmin G3X log file")

        # Convert the rest to dict
        metadata = {}
        for meta in metadata_text[1:]:
            match = re.fullmatch(r'(.*)="(.*)"', meta)
            if match:
                key, value = match.groups()
                metadata[key] = value

        # Read row 2 as stable column keys
        stable_keys_row = pandas.read_csv(log, skiprows=[0,1], nrows=1)
        stable_keys = dict(zip(stable_keys_row.columns, stable_keys_row.iloc[0]))

        # Parse CSV
        df = pandas.read_csv(log, skiprows=[0,2])

        # Store the stable key mapping for cross-file analysis
        df.attrs['stable_keys'] = stable_keys

        if df.empty:
            # If file has zero data, recommend deleting, for now just skip
            flight_type = "empty"
        else:
            if df["Oil Press (PSI)"].max() < 1:
                # If no oil pressure in all of log, assume this session was testing/configuration
                flight_type = "config"
            elif df["GPS Ground Speed (kt)"].max() < 50:
                # If airplane did not achieve a ground speed sufficient for flight, assume taxi-only
                flight_type = "flight"
            else:
                # Otherwise, the airplane was flying
                flight_type = "flight"

            if log_path:
                # Copy the file into the correct destination path, preserving modification time
                dest_file = os.path.join(log_path, flight_type, os.path.basename(log))
                if not os.path.exists(dest_file):
                    shutil.copy2(log, dest_file)

        # Print out flight type
        if args.verbose:
            print(f"{os.path.basename(log)}: {metadata['aircraft_ident']} {metadata['product']} {metadata['unit']} {metadata['software_version']} {flight_type}")

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()