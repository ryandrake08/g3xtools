#!/usr/bin/env python3
"""
G3X Aviation Database Downloader and SD Card Creator

Downloads current navigation database updates from Garmin's fly.garmin.com service
for G3X aircraft systems and creates complete SD card images ready for installation.

This tool orchestrates the complete workflow:
1. Authenticates with Garmin services (via garmin_login module)
2. Discovers aircraft and their devices (via garmin_api module)
3. Catalogs available database updates as JSON descriptors
4. Downloads navigation databases and auxiliary files conditionally
5. Extracts TAW archives and copies files to create SD card images

Features:
- OAuth authentication with automatic token caching
- Conditional downloads using HTTP If-Modified-Since headers
- Two-phase operation: discovery + download for efficient processing
- TAW archive extraction for navigation databases
- Preserves directory structure for auxiliary files
- Verbose output and error handling for debugging

Example usage:
    python3 g3xdata.py -l                              # List aircraft
    python3 g3xdata.py -a 12345 -d 67890               # Download databases
    python3 g3xdata.py -a 12345 -d 67890 -o /sdcard    # Create SD card image
"""

import argparse
import datetime
import json
import pathlib
import platformdirs
import requests
import shutil
import urllib.parse

def download_file(url: str, dest_path: pathlib.Path, expected_size: int | None = None, verbose: bool = False) -> bool:
    """Download a file with conditional headers if it already exists."""
    headers = {}

    # Check if file already exists and set If-Modified-Since header
    if dest_path.exists():
        # Get the modification time and format it for HTTP header
        mtime = dest_path.stat().st_mtime
        if_modified_since = datetime.datetime.fromtimestamp(mtime).strftime('%a, %d %b %Y %H:%M:%S GMT')
        headers['If-Modified-Since'] = if_modified_since

        if verbose:
            print(f"    File exists, checking if modified since {if_modified_since}")

    # Create parent directories if they don't exist
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        session = requests.Session()
        session.headers['User-Agent'] = None  # type: ignore
        resp = session.get(url, headers=headers, stream=True)

        if resp.status_code == 304:
            if verbose:
                print(f"    File not modified, skipping download")
            return False  # File not modified

        resp.raise_for_status()

        if verbose:
            print(f"    Downloading {url} -> {dest_path}")
            if expected_size:
                print(f"    Expected size: {expected_size} bytes")

        # Download the file
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Verify file size if expected_size is provided
        actual_size = dest_path.stat().st_size
        if expected_size and actual_size != expected_size:
            print(f"    Warning: Expected {expected_size} bytes, got {actual_size} bytes")

        return True  # File downloaded

    except requests.RequestException as e:
        print(f"    Error downloading {url}: {e}")
        return False

def download_files_in(files_list: list[dict], cache_root: pathlib.Path, skip: bool = False, verbose: bool = False) -> list:
    """Download a list of files from files_data structure."""
    dest_paths = []

    for file_info in files_list:
        url = file_info['url']
        destination = file_info.get('destination')
        file_size = file_info.get('fileSize')

        if destination:
            # Filename destination is specified, place it there
            dest_path = cache_root / pathlib.PurePosixPath(destination)
            if verbose:
                print(f"  Destination filename is: {destination}")
        else:
            # Extract filename from URL and place in cache_root
            filename = pathlib.Path(urllib.parse.urlparse(url).path).name
            dest_path = cache_root / filename
            if verbose:
                print(f"  No destination specified, using: {filename}")

        dest_paths.append(dest_path)

        if not skip:
            download_file(url, dest_path, file_size, verbose)

    return dest_paths

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download G3X data update and create SD card')
    parser.add_argument('-T', '--access-token', help='Specify flygarmin access token')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    # List aircraft and devices
    parser.add_argument('-l', '--list', action='store_true', help='List aircraft IDs and device IDs for each aircraft')
    # Download
    parser.add_argument('-c', '--clear-cache', action='store_true', help='Delete all cached downloaded data, will cause all data to be re-downloaded')
    parser.add_argument('-u', '--update', action='store_true', help='Update to the latest installable data offered by flygarmin. If not set, uses existing data')
    parser.add_argument('-a', '--aircraft-id', help='Specify aircraft ID')
    parser.add_argument('-d', '--device-id', help='Specify device ID')
    # Update SDCard
    parser.add_argument('-o', '--output', help='Specify output path (usually an SD card)')
    # Development/debug arguments
    parser.add_argument('--dump-auth-json', help='Output a file containing the authentication record returned from flygarmin (for DEBUG only)')
    parser.add_argument('--auth-json', help='Specify file containing the authentication record, to avoid request to flygarmin (for DEBUG only)')
    parser.add_argument('--dump-aircraft-json', help='Output a file containing an aircraft descriptor and then exit (for DEBUG only)')
    parser.add_argument('--aircraft-json', help='Specify file containing an aircraft descriptor, to avoid request to flygarmin (for DEBUG only)')
    parser.add_argument('--no-download-data', action='store_true', help='Skip actual data file download and use files in the cache (for DEBUG only)')
    args = parser.parse_args()

    from garmin_login import flygarmin_get_access_token
    from garmin_api import flygarmin_list_aircraft, flygarmin_list_files

    # Directories for intermediate data
    datasets_path = platformdirs.user_data_path("g3xavdb", "g3xavdb")
    caches_path = platformdirs.user_cache_path("g3xavdb", "g3xavdb")

    # We only need aircraft data if we are updating
    if args.update:
        if args.aircraft_json:
            # Use the provided aircraft descriptor file instead of making API calls
            with open(args.aircraft_json, encoding="utf-8") as fd:
                aircraft_data = json.load(fd)

        else:
            # Need to obtain an aircraft descriptor from garmin, this requires an access token
            access_token = args.access_token or flygarmin_get_access_token(args.auth_json, args.dump_auth_json)

            # Query garmin for the aircraft data
            aircraft_data = flygarmin_list_aircraft(access_token)

            # Optionally dump the aircraft data
            if args.dump_aircraft_json:
                with open(args.dump_aircraft_json, "w", encoding="utf-8") as fd:
                    json.dump(aircraft_data, fd, indent=2)

        if args.list:
            # List the aircraft and devices and exit
            for aircraft in aircraft_data:
                device_ids = [str(device['id']) for device in aircraft['devices']]
                print(f"Aircraft: {aircraft['id']}: Devices: {', '.join(device_ids)}")
            return

        # Clear the dataset directory because we are going to download new descriptors
        if datasets_path.exists():
            if args.verbose:
                print("Clearing data directory")
            shutil.rmtree(datasets_path)
        datasets_path.mkdir(parents=True, exist_ok=True)

        if args.aircraft_id and args.device_id:
            # Download the current installable series/issue of all avdb types for this aircraft / device combination
            aircraft = next((a for a in aircraft_data if str(a['id']) == args.aircraft_id), None)
            if aircraft is None:
                raise KeyError

            device = next((d for d in aircraft['devices'] if str(d['id']) == args.device_id), None)
            if device is None:
                raise KeyError

            if args.verbose:
                print(f"Updating installable datasets for {aircraft['name']} {device['name']} from flygarmin")

            # Iterate through all installable series/issue combinations
            for avdb in device['avdbTypes']:
                for series in avdb['series']:
                    for issue in series['installableIssues']:
                        # Parse the date strings and check if issue is currently valid
                        effective_at = datetime.datetime.fromisoformat(issue['effectiveAt'].replace('Z', '+00:00'))
                        invalid_at = None if issue['invalidAt'] is None else datetime.datetime.fromisoformat(issue['invalidAt'].replace('Z', '+00:00'))
                        now = datetime.datetime.now().astimezone()

                        # Warn if we are outside dataset's validity window
                        if now < effective_at:
                            print(f"Warning: dataset: {avdb['name']}, series: {series['region']['name']}, issue: {issue['name']} becomes effective {effective_at}")

                        if invalid_at and now >= invalid_at:
                            print(f"Warning: dataset: {avdb['name']}, series: {series['region']['name']}, issue: {issue['name']} expired {invalid_at}")

                        # Get the dataset descriptor for this series/issue
                        try:
                            files_data = flygarmin_list_files(series['id'], issue['name'])
                        except Exception as e:
                            print(f"Error getting file list for series {series['id']}, issue {issue['name']}: {e}")
                            continue

                        # Save dataset descriptor to file
                        dataset_file = datasets_path / f"{avdb['id']}-{series['id']}-{issue['name']}.json"
                        with open(dataset_file, 'w', encoding='utf-8') as fd:
                            json.dump(files_data, fd, indent=2)

                        if args.verbose:
                            print(f"Available dataset: {avdb['name']}, series: {series['region']['name']}, issue: {issue['name']}, revision: {issue['revision']}")

    # Clear cache if requested
    if args.clear_cache:
        if args.verbose:
            print("Clearing download cache")

        if caches_path.exists():
            shutil.rmtree(caches_path)
        caches_path.mkdir(parents=True, exist_ok=True)

    # Download files for each dataset descriptor
    taw_files = []
    copy_files = []
    for dataset_file in datasets_path.glob("*.json"):
        if args.verbose:
            print(f"Processing dataset described in: {dataset_file.name}")

        # Read the dataset descriptor
        with open(dataset_file, 'r', encoding='utf-8') as fd:
            files_data = json.load(fd)

        # Download main files
        if 'mainFiles' in files_data:
            main_files = download_files_in(files_data['mainFiles'], caches_path / "mainFiles", args.no_download_data, args.verbose)
            taw_files.extend(main_files)

        # Download auxiliary files
        if 'auxiliaryFiles' in files_data:
            auxiliary_files = download_files_in(files_data['auxiliaryFiles'], caches_path / "auxiliaryFiles", args.no_download_data, args.verbose)
            copy_files.extend(auxiliary_files)

    from taw import extract_taw

    if args.output:
        # Extract each file in taw_files to the root sdcard
        for taw_file in taw_files:
            if args.verbose:
                print(f"Extracting {taw_file} to {args.output}")
            extract_taw(str(taw_file), args.output, info_only=False, verbose=args.verbose)

        # Copy each file in copy_files to the root sdcard, preserving the relative path
        for copy_file in copy_files:
            # Calculate relative path from auxiliaryFiles directory to preserve directory structure
            relative_path = copy_file.relative_to(caches_path / "auxiliaryFiles")
            dest_path = pathlib.Path(args.output) / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if args.verbose:
                print(f"Copying {copy_file} to {dest_path}")
            shutil.copy2(copy_file, dest_path)

if __name__ == "__main__":
    main()
