#!/usr/bin/env python3

import argparse
import csv
import glob
import os
import sys

class G3XLogFileData:

    # initialize with filename
    def __init__(self, filename):
        # store the filename
        self.filename = filename

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()

    def open(self):
        # open the file
        self.file = open(self.filename)

        # read it as a csv
        self.csv_reader = csv.reader(self.file, delimiter = ',')

        # first line is airframe information
        airframe_infos = next(self.csv_reader)
        self.airframe_info = {key: val.strip('\"') for key, val in dict(x.split('=') for x in airframe_infos[1:]).items()}

        # second and third lines are headers
        self.full_headers = next(self.csv_reader)
        self.short_headers = next(self.csv_reader)

        # leave the file ready at the first line of actual data
        return self

    def close(self):
        self.file.close()

def compare_headers(prev_file, curr_file):
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
            if curr_stable_keys.get(new_header):
                # Look for old header with same stable key
                for old_header in list(removed_headers):
                    if (prev_stable_keys and
                        prev_stable_keys.get(old_header) == curr_stable_keys.get(new_header)):
                        renamed_headers.append(f"{old_header} -> {new_header} ({curr_stable_keys.get(new_header)})")
                        new_headers.discard(new_header)
                        removed_headers.discard(old_header)
                        break

        # Only report changes if there are actual structural changes
        if new_headers or removed_headers or renamed_headers:
            print(f"{os.path.basename(curr_file.filename)}: File structure changed: {prev_software_version} -> {curr_software_version}")

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

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Analyze Garmin G3X aircraft data logs looking for structure differences')
    parser.add_argument('search_path', nargs='?', help='Path to search for log files')
    args = parser.parse_args()

    log_path = args.search_path or os.getenv('G3X_LOG_PATH')
    if not log_path:
        print("Error: Logs path must be provided via G3X_LOG_PATH environment variable or command line argument", file=sys.stderr)
        sys.exit(1)

    # Search recursively for G3X log files (log_*.csv)
    src_logs = sorted(glob.glob(f"{log_path}/**/log_*.csv", recursive=True), key=os.path.basename)

    # Process files and compare headers
    prev_file_data = None

    for filename in src_logs:
        with G3XLogFileData(filename) as curr_file:
            if prev_file_data:
                compare_headers(prev_file_data, curr_file)

            # Store current file data for next comparison
            class FileData:
                def __init__(self, filename, full_headers, short_headers, airframe_info):
                    self.filename = filename
                    self.full_headers = full_headers
                    self.short_headers = short_headers
                    self.airframe_info = airframe_info

            prev_file_data = FileData(curr_file.filename, curr_file.full_headers, curr_file.short_headers, curr_file.airframe_info)

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()