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
import os
import re
import shutil
import sys
from pathlib import Path

# Classification thresholds
OIL_PRESSURE_THRESHOLD_PSI = 1  # Minimum oil pressure to indicate engine running
GROUND_SPEED_THRESHOLD_KT = 50  # Minimum ground speed to indicate flight vs taxi

def main() -> None:
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process and categorize Garmin G3X aircraft data logs')
    parser.add_argument('search_path', nargs='?', help='Path to search for data_log directories')
    parser.add_argument('-o', '--output', help='Output directory for processed logs')
    parser.add_argument('-v', '--verbose', action='store_true', help='Output metadata information for each log file')
    args = parser.parse_args()

    # Determine search path: command line > environment > error
    mount_root_str = args.search_path or os.getenv('G3X_SEARCH_PATH')
    if not mount_root_str:
        print("Error: Search path must be provided via G3X_SEARCH_PATH environment variable or command line argument", file=sys.stderr)
        sys.exit(1)

    mount_root = Path(mount_root_str).resolve()

    # Validate search path exists and is a directory
    if not mount_root.exists():
        print(f"Error: Search path does not exist: {mount_root}", file=sys.stderr)
        sys.exit(1)
    if not mount_root.is_dir():
        print(f"Error: Search path is not a directory: {mount_root}", file=sys.stderr)
        sys.exit(1)

    # Search recursively for G3X log files (log_*.csv)
    src_logs = sorted(mount_root.glob("**/log_*.csv"))

    # Determine output path: command line > environment. If not specified, no files are output
    log_path_str = args.output or os.getenv('G3X_LOG_PATH')
    log_path = Path(log_path_str).resolve() if log_path_str else None

    # Create destination subfolders
    if log_path:
        for subdir in ["config", "flight", "taxi"]:
            (log_path / subdir).mkdir(parents=True, exist_ok=True)

    # Process each log source
    for log in src_logs:

        # Single-pass file read: metadata, CSV structure, and data processing
        with open(log) as file:
            # Row 0: Read metadata line
            first_line = file.readline()
            metadata_text = first_line.strip().split(",")

            # Verify first item
            if not metadata_text or metadata_text[0] != "#airframe_info":
                raise ValueError(f"Not a Garmin G3X log file: {log}")

            # Convert the rest to dict with validation
            metadata = {}
            required_keys = ['log_version', 'log_content_version', 'product', 'aircraft_ident', 'unit_software_part_number', 'software_version', 'system_id', 'unit', 'airframe_hours', 'engine_hours']
            for meta in metadata_text[1:]:
                match = re.fullmatch(r'(.*)="(.*)"', meta)
                if match:
                    groups: tuple[str, str] = match.groups()  # type: ignore[assignment]
                    key, value = groups
                    metadata[key] = value

            # Validate required metadata keys exist
            missing_keys = [key for key in required_keys if key not in metadata]
            if missing_keys:
                raise ValueError(f"Missing required metadata in {log}: {', '.join(missing_keys)}")

            # Row 1: Skip display headers
            file.readline()

            # Row 2: Read stable keys
            stable_keys_line = file.readline().strip()
            if not stable_keys_line:
                raise ValueError(f"Missing stable keys row in {log}")
            stable_keys = stable_keys_line.split(',')

            # Validate required columns exist
            try:
                oil_press_idx = stable_keys.index('E1 OilP')
                ground_speed_idx = stable_keys.index('GndSpd')
            except ValueError as e:
                raise ValueError(f"Missing required column in {log}: {e}")

            # Read data rows and find max values using CSV reader
            reader = csv.reader(file)
            oil_press_max = 0
            ground_speed_max = 0
            data_rows = 0

            for row in reader:
                if len(row) > max(oil_press_idx, ground_speed_idx):
                    data_rows += 1
                    try:
                        oil_press = int(row[oil_press_idx])
                        ground_speed = float(row[ground_speed_idx])
                        oil_press_max = max(oil_press_max, oil_press)
                        ground_speed_max = max(ground_speed_max, ground_speed)
                    except (ValueError, IndexError) as e:
                        raise ValueError(f"Invalid data in log file {log}: {e}")

        # Classify flight type based on collected data
        if data_rows == 0:
            # If file has zero data, recommend deleting, for now just skip
            flight_type = "empty"
        else:
            if oil_press_max < OIL_PRESSURE_THRESHOLD_PSI:
                # If no oil pressure in all of log, assume this session was testing/configuration
                flight_type = "config"
            elif ground_speed_max < GROUND_SPEED_THRESHOLD_KT:
                # If airplane did not achieve a ground speed sufficient for flight, assume taxi-only
                flight_type = "taxi"
            else:
                # Otherwise, the airplane was flying
                flight_type = "flight"

            if log_path:
                # Copy the file into the correct destination path, preserving modification time
                dest_file = log_path / flight_type / log.name
                if not dest_file.exists():
                    shutil.copy2(log, dest_file)

        # Print out flight type
        if args.verbose:
            print(f"{log.name}: {metadata['aircraft_ident']} {metadata['product']} {metadata['unit']} {metadata['software_version']} {flight_type}")

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()
