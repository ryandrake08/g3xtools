#!/usr/bin/env python3
"""
Garmin G3X Log Structure Analyzer

Analyzes Garmin G3X aircraft data log files to detect structural changes across
different software versions. Compares column headers and stable keys between
consecutive log files to identify:
- New columns added
- Columns removed
- Columns renamed (detected via stable key matching)

Usage:
    python3 g3xheaders.py /path/to/logs

Environment Variables:
    G3X_LOG_PATH: Default path to search for log files

The tool processes log_*.csv files in chronological order (sorted by basename)
and reports structural differences with software version information.
"""

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

class G3XLogFileData:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def __enter__(self) -> 'G3XLogFileData':
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.close()

    def open(self) -> 'G3XLogFileData':
        self.file = open(self.filename, encoding='utf-8')
        self.csv_reader = csv.reader(self.file)

        # Parse airframe information from first line
        airframe_infos = next(self.csv_reader)
        try:
            self.airframe_info: Dict[str, str] = {key: val.strip('\"') for key, val in dict(x.split('=') for x in airframe_infos[1:]).items()}
        except ValueError as e:
            raise ValueError(f"Invalid airframe metadata format in {self.filename}: {e}")

        # Read headers and stable keys
        self.full_headers: List[str] = next(self.csv_reader)
        self.short_headers: List[str] = next(self.csv_reader)

        return self

    def close(self) -> None:
        self.file.close()

def compare_headers(prev_file: G3XLogFileData, curr_file: G3XLogFileData) -> bool:
    """Compare headers between two G3X files and report changes"""
    prev_headers = prev_file.full_headers
    prev_stable_keys = dict(zip(prev_file.full_headers, prev_file.short_headers))
    prev_software_version = prev_file.airframe_info.get('software_version', 'unknown')

    curr_headers = curr_file.full_headers
    curr_stable_keys = dict(zip(curr_file.full_headers, curr_file.short_headers))
    curr_software_version = curr_file.airframe_info.get('software_version', 'unknown')

    # Check if headers match
    if curr_headers != prev_headers:
        # Find new, changed, and removed headers
        prev_header_set = set(prev_headers)
        curr_header_set = set(curr_headers)

        new_headers = curr_header_set - prev_header_set
        removed_headers = prev_header_set - curr_header_set

        # Find renamed headers (same stable key, different header name)
        renamed_headers = []
        for new_header in list(new_headers):
            stable_key = curr_stable_keys.get(new_header)
            if stable_key:
                # Find old header with same stable key
                old_header = next((h for h in removed_headers if prev_stable_keys.get(h) == stable_key), None)
                if old_header:
                    renamed_headers.append(f"{old_header} -> {new_header} ({stable_key})")
                    new_headers.discard(new_header)
                    removed_headers.discard(old_header)

        # Only report changes if there are actual structural changes
        if new_headers or removed_headers or renamed_headers:
            print(f"{Path(curr_file.filename).name}: File structure changed: {prev_software_version} -> {curr_software_version}")

            if new_headers:
                new_with_keys = [f"{h} ({curr_stable_keys.get(h, 'no key')})" for h in new_headers]
                print(f"  New: {', '.join(new_with_keys)}")
            if renamed_headers:
                print(f"  Renamed: {', '.join(renamed_headers)}")
            if removed_headers:
                removed_with_keys = [f"{h} ({prev_stable_keys.get(h, 'no key') if prev_stable_keys else 'no key'})" for h in removed_headers]
                print(f"  Removed: {', '.join(removed_with_keys)}")
            return True
    return False

def main() -> None:
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Analyze Garmin G3X aircraft data logs looking for structure differences')
    parser.add_argument('search_path', nargs='?', help='Path to search for log files')
    args = parser.parse_args()

    log_path_str = args.search_path or os.getenv('G3X_LOG_PATH')
    if not log_path_str:
        print("Error: Logs path must be provided via G3X_LOG_PATH environment variable or command line argument", file=sys.stderr)
        sys.exit(1)

    log_path = Path(log_path_str)

    # Search recursively for G3X log files (log_*.csv)
    src_logs = sorted(log_path.glob("**/log_*.csv"), key=lambda p: p.name)

    # Process files and compare headers
    for prev_filename, curr_filename in zip(src_logs, src_logs[1:]):
        with G3XLogFileData(prev_filename) as prev_file, G3XLogFileData(curr_filename) as curr_file:
            compare_headers(prev_file, curr_file)

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()