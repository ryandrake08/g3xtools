#!/usr/bin/env python3
"""
G3X Aviation Database Downloader and SD Card Creator

Downloads current navigation database updates from Garmin's fly.garmin.com service
for G3X aircraft systems and creates complete SD card images ready for installation.

This tool orchestrates the complete workflow:
1. Authenticates with flygarmin services (via garmin_login module)
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
import sys
import urllib.parse

from garmin_login import flygarmin_login
from garmin_api import flygarmin_list_aircraft, flygarmin_list_files, flygarmin_unlock
from taw import extract_taw
from vsn import read_vsn

CACHE_PATH = platformdirs.user_cache_path("g3xavdb", "g3xavdb", ensure_exists=True)
GARMIN_SECURITY_ID = 1727

session = requests.Session()
session.headers['User-Agent'] = None  # type: ignore

def cache_json_data(cache_filename: str, fetch_function, force: bool = False):
    """Helper function to cache JSON data with consistent pattern.

    Args:
        cache_filename: Name of cache file (e.g., "garmin_auth.json")
        fetch_function: Function to call if cache miss or force refresh
        force: If True, ignore cache and fetch fresh data

    Returns:
        Cached or freshly fetched data
    """
    cache_path = CACHE_PATH / cache_filename

    if force:
        cache_path.unlink(missing_ok=True)

    try:
        with open(cache_path, encoding="utf-8") as fd:
            return json.load(fd)
    except FileNotFoundError:
        data = fetch_function()
        with open(cache_path, "w", encoding="utf-8") as fd:
            json.dump(data, fd, indent=2)
        return data

def get_access_token(force: bool = False) -> str:
    """Obtain OAuth access token either from data directory or by performing a login."""
    auth_data = cache_json_data("garmin_auth.json", flygarmin_login, force)
    return auth_data['access_token']

def get_aircraft_data(access_token: str, force: bool = False) -> list:
    """Obtain aircraft data either from the data directory or through flygarmin api."""
    return cache_json_data("aircraft.json", lambda: flygarmin_list_aircraft(access_token), force)

def get_dataset_files(series_id: int, issue_name: str, force: bool = False) -> dict:
    """Obtain dataset descriptor either from the data directory or through flygarmin api."""
    cache_filename = f"dataset-{series_id}-{issue_name}.json"
    return cache_json_data(cache_filename, lambda: flygarmin_list_files(series_id, issue_name), force)

def get_unlock_data(access_token: str, series_id: int, issue_name: str, device_id: int, card_serial: int, force: bool = False) -> dict:
    """Obtain unlock data either from cache or through flygarmin API."""
    cache_filename = f"unlock-{series_id}-{issue_name}-{device_id}-{card_serial:08X}.json"
    return cache_json_data(cache_filename, lambda: flygarmin_unlock(access_token, series_id, issue_name, device_id, card_serial), force)

def get_system_serial(aircraft_data: list, device_id: int) -> int | None:
    """Get system serial number for a given device ID from aircraft data.

    Args:
        aircraft_data: List of aircraft dictionaries from flygarmin API
        device_id: Target device ID to find serial for

    Returns:
        Device serial number as integer, or None if not found
    """
    for aircraft in aircraft_data:
        for device in aircraft['devices']:
            if device['id'] == device_id:
                return device['serial']
    return None

def list_aircraft_devices(aircraft_data):
    """List all aircraft and their devices, then exit."""
    for aircraft in aircraft_data:
        device_info = [f"{device['name']} ({device['id']})" for device in aircraft['devices']]
        print(f"Aircraft: {aircraft['id']}: Devices: {', '.join(device_info)}")
    sys.exit(0)

def get_cached_file_path_for_url(url: str) -> pathlib.Path:
    """Generate cache file path for a given URL with proper directory structure.

    Args:
        url: The URL to generate a cache path for

    Returns:
        Path object pointing to the cached file location
        Directory structure: CACHE_PATH/hostname/url_path

    Note:
        Creates parent directories if they don't exist.
        Uses PurePosixPath for URL parsing to handle cross-platform compatibility.
    """
    # Parse URL to create destination path from hostname + path
    parsed_url = urllib.parse.urlparse(url)
    hostname_path = pathlib.PurePosixPath(parsed_url.hostname or "avdb.garmin.com")
    url_path = pathlib.PurePosixPath(parsed_url.path.lstrip('/'))  # Remove leading slash
    dest_path = CACHE_PATH / hostname_path / url_path

    # Check if file already exists
    if dest_path.exists():
        return dest_path

    # Create parent directories if they don't exist
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    return dest_path

def download_file(url: str, expected_size: int) -> pathlib.Path:
    """Download a file with conditional headers if it already exists."""
    dest_path = get_cached_file_path_for_url(url)

    # Skip downloading if file already exists
    if not dest_path.exists():
        resp = session.get(url, stream=True)
        resp.raise_for_status()

        # Download the file
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    # Verify file size if expected_size is provided
    actual_size = dest_path.stat().st_size
    if actual_size != expected_size:
        print(f"Warning: {dest_path}: Expected {expected_size} bytes, got {actual_size} bytes", file=sys.stderr)

    return dest_path

def update_feature_unlock(dest_dir: pathlib.Path, region_path: str, card_serial: int, security_id: int, system_serial: int):
    from featunlk import FILENAME_TO_FEATURE, CHUNK_SIZE, Feature, NAVIGATION_PREVIEW_START, NAVIGATION_PREVIEW_END, update_feat_unlk
    from checksum import feat_unlk_checksum

    feature = FILENAME_TO_FEATURE.get(region_path)
    if feature is None:
        raise ValueError(f"Unsupported region: {region_path}")

    preview = None
    dest_path = dest_dir / region_path
    with open(dest_path, 'rb') as data:
        last_block = block = data.read(CHUNK_SIZE)

        if feature == Feature.NAVIGATION:
            preview = block[NAVIGATION_PREVIEW_START:NAVIGATION_PREVIEW_END]

        chk = 0xFFFFFFFF
        while block:
            last_block = block
            chk = feat_unlk_checksum(block, chk)
            block = data.read(CHUNK_SIZE)

    if chk != 0:
        raise ValueError(f"{dest_path} failed the checksum")

    checksum = int.from_bytes(last_block[-4:], 'little')

    update_feat_unlk(dest_dir, feature, card_serial, security_id, system_serial, checksum, preview)

def installable_databases(aircraft_data: list):
    """Generate all installable series/issue combinations for all aircraft devices.

    Args:
        aircraft_data: List of aircraft dictionaries from flygarmin API

    Yields:
        Tuple of (series_id, issue_name, device_id) for each valid dataset

    Note:
        Filters out datasets that are not currently valid based on effective/invalid dates.
        Prints warnings for datasets outside their validity window.
    """
    # Generate all installable series/issue combinations
    for aircraft in aircraft_data:
        for device in aircraft['devices']:
            for avdb in device['avdbTypes']:
                for series in avdb['series']:
                    for issue in series['installableIssues']:
                        # Parse the date strings and check if issue is currently valid
                        effective_at = datetime.datetime.fromisoformat(issue['effectiveAt'].replace('Z', '+00:00'))
                        invalid_at = None if issue['invalidAt'] is None else datetime.datetime.fromisoformat(issue['invalidAt'].replace('Z', '+00:00'))
                        now = datetime.datetime.now().astimezone()

                        # Warn if we are outside dataset's validity window
                        if now < effective_at:
                            print(f"Warning: dataset: {avdb['name']}, series: {series['region']['name']} ({series['id']}), issue: {issue['name']} becomes effective {effective_at}", file=sys.stderr)

                        if invalid_at and now >= invalid_at:
                            print(f"Warning: dataset: {avdb['name']}, series: {series['region']['name']} ({series['id']}), issue: {issue['name']} expired {invalid_at}", file=sys.stderr)

                        # Add to generator
                        yield (series['id'], issue['name'], device['id'])

def main():
    # Build platform-specific device example
    if sys.platform == 'darwin':
        device_example = "/dev/rdisk2s1"
    elif sys.platform.startswith('linux'):
        device_example = "/dev/sdb1"
    elif sys.platform == 'win32':
        device_example = "D:"
    else:
        device_example = "/dev/block_device"

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download G3X data update and create SD card')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')

    # FlyGarmin controls
    parser.add_argument('-F', '--force-login', action='store_true', help='Force a refresh of the flygarmin access token')
    parser.add_argument('-T', '--access-token', help='Specify flygarmin access token')

    # Working with aircraft and devices
    parser.add_argument('-A', '--force-refresh-aircraft', action='store_true', help='Force a refresh of the aircraft data')
    parser.add_argument('-l', '--list-devices', action='store_true', help='List aircraft IDs and avionics device IDs for each aircraft')

    # Download
    parser.add_argument('-D', '--force-refresh-datasets', action='store_true', help='Force a refresh of the dataset data')

    # Update SDCard
    parser.add_argument('-U', '--force-refresh-unlock-codes', action='store_true', help='Force a refresh of the unlock codes')
    parser.add_argument('-d', '--device-id', help='Specify avionics device ID')
    parser.add_argument('-o', '--output', help='Specify output path (usually an SD card)')
    parser.add_argument('-s', '--sddevice', help=f"Specify SD card block device. This is required for building feat_unlk.dat and requires root privileges. Example: {device_example}")
    parser.add_argument('-N', '--vsn', help="Specify SD card volume serial number for building feat_unlk.dat. Does not require root privileges")

    # Development/debug arguments
    args = parser.parse_args()

    # Get access token either from the comand line, from the auth_json, or from flygarmin
    access_token = args.access_token or get_access_token(args.force_login)

    # Get aircraft data either from aircraft_json or from flygarmin
    aircraft_data = get_aircraft_data(access_token, args.force_refresh_aircraft)

    # List the aircraft and devices and exit
    args.list_devices and list_aircraft_devices(aircraft_data) # type: ignore

    # Iterate through all installable series/issue combinations
    for series_id, issue_name, _ in installable_databases(aircraft_data):
        if args.verbose:
            print(f"Downloading files for series {series_id}, issue {issue_name}")

        # Get the dataset descriptor for this series/issue
        files_data = get_dataset_files(series_id, issue_name, args.force_refresh_datasets)

        # Download all files (main and auxiliary)
        for file_info in files_data.get('mainFiles', []) + files_data.get('auxiliaryFiles', []):
            if args.verbose:
                print(f"Downloading {file_info['url']}, expected size: {file_info['fileSize']}")

            download_file(file_info['url'], file_info['fileSize'])

    # Read the sdcard's serial number if it's not provided
    card_serial = int(args.vsn, 16) if args.vsn else read_vsn(args.sddevice) if args.sddevice else None

    # Get system serial from aircraft data
    system_serial = get_system_serial(aircraft_data, int(args.device_id))

    if args.device_id and args.output and card_serial and system_serial:
        if args.verbose:
            print(f"Creating SD card (s/n: {card_serial:08X}) at {args.output}, installable on device {args.device_id}")

        # Iterate through all installable series/issue combinations
        for series_id, issue_name, device_id in installable_databases(aircraft_data):
            # Skip if this dataset is for a different device
            if device_id != int(args.device_id):
                continue

            if args.verbose:
                print(f"Adding to SD card series {series_id}, issue {issue_name}")

            # Receive unlock information for each database
            #unlock_data = get_unlock_data(access_token, series_id, issue_name, device_id, card_serial, args.force_refresh_unlock_codes)

            # Find unlock code for our device
            #unlock_code = next((item['unlockCode'] for item in unlock_data['unlockCodes'] if item['deviceID'] == device_id)), None

            # Get the dataset descriptor for this series/issue
            files_data = get_dataset_files(series_id, issue_name)

            # Verfiy the main file is a TAW
            if files_data['issueType'] != "TAW":
                print(f"Warning: Unexpected issue type {files_data['issue_type']} for series {series_id}, issue {issue_name}", file=sys.stderr)
                continue

            # Get a path for the root output directory
            output_path = pathlib.Path(args.output)

            # Extract main files
            for file_info in files_data.get('mainFiles', []):
                # Get destination path
                cached_path = get_cached_file_path_for_url(file_info['url'])

                # Extract each file to the root sdcard
                for region_path, output_file_path in extract_taw(cached_path, output_path, skip_unknown_regions=True, verbose=args.verbose):
                    if args.verbose:
                        print(f"Extracted {cached_path} taw region {region_path} to {output_file_path}")
                    if region_path:
                        update_feature_unlock(output_path, region_path, card_serial, GARMIN_SECURITY_ID, system_serial)

            # Copy auxiliary files
            for file_info in files_data.get('auxiliaryFiles', []):
                # Get destination path
                cached_path = get_cached_file_path_for_url(file_info['url'])

                # Copy each file to the root sdcard, preserving the destination path
                output_file_path = output_path / pathlib.PurePosixPath(file_info['destination'])
                output_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cached_path, output_file_path)

                if args.verbose:
                    print(f"Copied {cached_path} to {args.output}")

if __name__ == "__main__":
    main()
