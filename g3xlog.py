#!/usr/bin/env python3

import argparse
import glob
import os
import pandas
import re
import subprocess
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

    # Determine output path: command line > environment > current directory
    log_path = args.output or os.getenv('G3X_LOG_PATH', os.getcwd())

    # Create destination subfolders
    [os.makedirs(log_path + f"/{subdir}", exist_ok=True) for subdir in ["config", "flight", "taxi"]]

    # Search recursively for G3X log files (log_*.csv)
    src_logs = glob.glob(mount_root + "/**/log_*.csv", recursive=True)

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

        # Output metadata information if verbose mode is enabled
        if args.verbose:
            print(f"{os.path.basename(log)}: {metadata['aircraft_ident']} {metadata['product']} {metadata['unit']} {metadata['software_version']}")

        # Parse CSV
        df = pandas.read_csv(log, skiprows=[0,2])

        if df.empty:
            # If file has zero data, recommend deleting, for now just skip
            if args.verbose:
                print(f"{os.path.basename(log)}: empty")
        else:
            if df["Oil Press (PSI)"].max() < 1:
                # If no oil pressure in all of log, assume this session was testing/configuration
                dest_path = log_path + "/config/"
                if args.verbose:
                    print(f"{os.path.basename(log)}: config")
            elif df["GPS Ground Speed (kt)"].max() < 50:
                # If airplane did not achieve a ground speed sufficient for flight, assume taxi-only
                dest_path = log_path + "/taxi/"
                if args.verbose:
                    print(f"{os.path.basename(log)}: taxi")
            else:
                # Otherwise, the airplane was flying
                dest_path = log_path + "/flight/"
                if args.verbose:
                    print(f"{os.path.basename(log)}: flight")

            # Call rsync to copy the file into the correct destination path
            subprocess.call(["rsync", "-t", "--ignore-existing", log, dest_path])

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()