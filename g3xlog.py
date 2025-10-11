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
    python3 g3xlog.py -v  # Auto-detect SD card

Environment Variables:
    G3X_SEARCH_PATH: Default search path for input log files
    G3X_LOG_PATH: Default output path for processed logs

The tool automatically discovers log_*.csv files recursively and copies them to
categorized subdirectories while preserving modification times. If no search path
is specified, the tool will attempt to auto-detect a mounted SD card.
"""

import argparse
import csv
import os
import pathlib
import re
import shutil
import sys
from typing import Optional

import sdcard

# Classification thresholds
_OIL_PRESSURE_THRESHOLD_PSI = 1  # Minimum oil pressure to indicate engine running
_GROUND_SPEED_THRESHOLD_KT = 50  # Minimum ground speed to indicate flight vs taxi


def _parse_log_metadata(log_path: pathlib.Path) -> dict[str, str]:
    """
    Parse metadata from G3X log file header.

    Args:
        log_path: Path to log file

    Returns:
        Dictionary of metadata key-value pairs

    Raises:
        ValueError: If file is not a valid G3X log or missing required metadata
    """
    required_keys = [
        'log_version', 'log_content_version', 'product', 'aircraft_ident',
        'unit_software_part_number', 'software_version', 'system_id', 'unit',
        'airframe_hours', 'engine_hours'
    ]

    with open(log_path) as file:
        # Row 0: Read metadata line
        first_line = file.readline()
        metadata_text = first_line.strip().split(",")

        # Verify first item
        if not metadata_text or metadata_text[0] != "#airframe_info":
            raise ValueError(f"Not a Garmin G3X log file: {log_path}")

        # Convert the rest to dict with validation
        metadata = {}
        for meta in metadata_text[1:]:
            match = re.fullmatch(r'(.*)="(.*)"', meta)
            if match:
                key, value = match.groups()
                metadata[key] = value

        # Validate required metadata keys exist
        missing_keys = [key for key in required_keys if key not in metadata]
        if missing_keys:
            raise ValueError(f"Missing required metadata in {log_path}: {', '.join(missing_keys)}")

    return metadata


def _analyze_log_data(log_path: pathlib.Path) -> tuple[int, float]:
    """
    Analyze log file to extract maximum oil pressure and ground speed.

    Args:
        log_path: Path to log file

    Returns:
        Tuple of (max_oil_pressure, max_ground_speed)

    Raises:
        ValueError: If file format is invalid or required columns missing
    """
    with open(log_path) as file:
        # Skip metadata line (row 0)
        file.readline()

        # Row 1: Skip display headers
        file.readline()

        # Row 2: Read stable keys
        stable_keys_line = file.readline().strip()
        if not stable_keys_line:
            raise ValueError(f"Missing stable keys row in {log_path}")
        stable_keys = stable_keys_line.split(',')

        # Validate required columns exist
        try:
            oil_press_idx = stable_keys.index('E1 OilP')
            ground_speed_idx = stable_keys.index('GndSpd')
        except ValueError as e:
            raise ValueError(f"Missing required column in {log_path}: {e}") from e

        # Read data rows and find max values using CSV reader
        reader = csv.reader(file)
        oil_press_max = 0
        ground_speed_max = 0.0

        for row in reader:
            if len(row) > max(oil_press_idx, ground_speed_idx):
                try:
                    oil_press = int(row[oil_press_idx])
                    ground_speed = float(row[ground_speed_idx])
                    oil_press_max = max(oil_press_max, oil_press)
                    ground_speed_max = max(ground_speed_max, ground_speed)
                except (ValueError, IndexError) as e:
                    raise ValueError(f"Invalid data in log file {log_path}: {e}") from e

    return oil_press_max, ground_speed_max


def _classify_flight_type(oil_press_max: int, ground_speed_max: float) -> str:
    """
    Classify flight type based on oil pressure and ground speed.

    Args:
        oil_press_max: Maximum oil pressure observed (PSI)
        ground_speed_max: Maximum ground speed observed (knots)

    Returns:
        Flight type: 'config', 'taxi', or 'flight'
    """
    if oil_press_max < _OIL_PRESSURE_THRESHOLD_PSI:
        # If no oil pressure in all of log, assume this session was testing/configuration
        return "config"
    elif ground_speed_max < _GROUND_SPEED_THRESHOLD_KT:
        # If airplane did not achieve a ground speed sufficient for flight, assume taxi-only
        return "taxi"
    else:
        # Otherwise, the airplane was flying
        return "flight"


def _find_log_files(search_path: pathlib.Path) -> list[pathlib.Path]:
    """
    Find all G3X log files in search path.

    Args:
        search_path: Directory to search recursively

    Returns:
        Sorted list of log file paths

    Raises:
        ValueError: If search path doesn't exist or isn't a directory
    """
    if not search_path.exists():
        raise ValueError(f"Search path does not exist: {search_path}")
    if not search_path.is_dir():
        raise ValueError(f"Search path is not a directory: {search_path}")

    return sorted(search_path.glob("**/log_*.csv"))


def _process_logs(
    search_path: pathlib.Path,
    output_path: Optional[pathlib.Path] = None,
    verbose: bool = False
) -> list[tuple[pathlib.Path, str, dict[str, str]]]:
    """
    Process all log files in search path and optionally copy to categorized directories.

    Args:
        search_path: Directory to search for log files
        output_path: Optional directory to copy categorized logs
        verbose: Whether to print verbose output

    Returns:
        List of tuples: (log_path, flight_type, metadata)

    Raises:
        ValueError: If files are invalid or paths don't exist
    """
    src_logs = _find_log_files(search_path)

    # Create destination subfolders
    if output_path:
        for subdir in ["config", "flight", "taxi"]:
            (output_path / subdir).mkdir(parents=True, exist_ok=True)

    results = []

    # Process each log source
    for log in src_logs:
        metadata = _parse_log_metadata(log)
        oil_press_max, ground_speed_max = _analyze_log_data(log)
        flight_type = _classify_flight_type(oil_press_max, ground_speed_max)

        if output_path and flight_type != "empty":
            # Copy the file into the correct destination path, preserving modification time
            dest_file = output_path / flight_type / log.name
            if not dest_file.exists():
                shutil.copy2(log, dest_file)

        # Print out flight type
        if verbose:
            print(f"{log.name}: {metadata['aircraft_ident']} {metadata['product']} {metadata['unit']} {metadata['software_version']} {flight_type}")

        results.append((log, flight_type, metadata))

    return results


def main() -> None:
    """CLI entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process and categorize Garmin G3X aircraft data logs')
    parser.add_argument('search_path', nargs='?', help='Path to search for data_log directories. If not specified, attempts to auto-detect SD card.')
    parser.add_argument('-o', '--output', help='Output directory for processed logs')
    parser.add_argument('-v', '--verbose', action='store_true', help='Output metadata information for each log file')
    args = parser.parse_args()

    # Determine search path: command line > environment > auto-detect
    mount_root_str = args.search_path or os.getenv('G3X_SEARCH_PATH') or sdcard.detect_sd_card()
    if not mount_root_str:
        print("Error: Search path must be provided via G3X_SEARCH_PATH environment variable, command line argument, or SD card must be mounted", file=sys.stderr)
        sys.exit(1)

    mount_root = pathlib.Path(mount_root_str).resolve()

    # Determine output path: command line > environment. If not specified, no files are output
    log_path_str = args.output or os.getenv('G3X_LOG_PATH')
    log_path = pathlib.Path(log_path_str).resolve() if log_path_str else None

    try:
        _process_logs(mount_root, log_path, args.verbose)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
