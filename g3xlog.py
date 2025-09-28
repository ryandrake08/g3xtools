#!/usr/bin/env python3
"""
Garmin G3X Log Processor

Processes and categorizes Garmin G3X aircraft data logs into flight types based on
operational characteristics. Analyzes CSV log files to determine if sessions were:
- config: Ground testing (no oil pressure)
- taxi: Ground operations only (max ground speed < 50kt)
- flight: Actual flight operations

Usage:
    python3 g3xlog.py /path/to/search -o /output/path -v

Environment Variables:
    G3X_SEARCH_PATH: Default search path for input log files
    G3X_LOG_PATH: Default output path for processed logs

The tool automatically discovers log_*.csv files recursively and copies them to
categorized subdirectories while preserving modification times.
"""

import argparse
import csv
import glob
import os
import re
import shutil
import sys

def main() -> None:
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

        # Parse CSV with standard library using stable keys
        with open(log, 'r') as file:
            # Skip metadata line (row 0)
            file.readline()  # Skip row 0 (metadata)
            file.readline()  # Skip row 1 (headers)
            stable_keys = file.readline().strip().split(',')  # Row 2 (stable keys)

            # Find column indices using stable keys
            oil_press_idx = stable_keys.index('E1 OilP')
            ground_speed_idx = stable_keys.index('GndSpd')

            # Read data rows and find max values
            reader = csv.reader(file)
            oil_press_max = 0
            ground_speed_max = 0
            data_rows = 0

            for row in reader:
                if len(row) > max(oil_press_idx, ground_speed_idx):
                    data_rows += 1
                    oil_press = int(row[oil_press_idx])
                    ground_speed = float(row[ground_speed_idx])
                    oil_press_max = max(oil_press_max, oil_press)
                    ground_speed_max = max(ground_speed_max, ground_speed)

        if data_rows == 0:
            # If file has zero data, recommend deleting, for now just skip
            flight_type = "empty"
        else:
            if oil_press_max < 1:
                # If no oil pressure in all of log, assume this session was testing/configuration
                flight_type = "config"
            elif ground_speed_max < 50:
                # If airplane did not achieve a ground speed sufficient for flight, assume taxi-only
                flight_type = "taxi"
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