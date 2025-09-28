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
from garmin_api import flygarmin_list_aircraft, flygarmin_list_files, flygarmin_unlock, flygarmin_list_series
from featunlk import update_feature_unlock, GARMIN_SECURITY_ID
from taw import extract_taw
from sdcard import read_vsn, detect_sd_card, get_platform_device_example

CACHE_PATH = platformdirs.user_cache_path("g3xavdb", "g3xavdb", ensure_exists=True)

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
    """Obtain OAuth access token with caching support.

    Args:
        force: If True, ignore cache and perform fresh login

    Returns:
        Valid OAuth access token string for API authentication
    """
    auth_data = cache_json_data("garmin_auth.json", flygarmin_login, force)
    return auth_data['access_token']

def get_aircraft_data(access_token: str, force: bool = False) -> list:
    """Obtain aircraft data with caching support.

    Args:
        access_token: Valid OAuth token for flygarmin API authentication
        force: If True, ignore cache and fetch fresh data from API

    Returns:
        List of aircraft dictionaries containing aircraft and device information
    """
    return cache_json_data("aircraft.json", lambda: flygarmin_list_aircraft(access_token), force)

def get_dataset_files(series_id: int, issue_name: str, force: bool = False) -> dict:
    """Obtain dataset file information with caching support.

    Args:
        series_id: Numeric identifier for the database series
        issue_name: String identifier for the specific issue (e.g., "2509")
        force: If True, ignore cache and fetch fresh data from API

    Returns:
        Dictionary containing file URLs, sizes, and destination paths for the dataset
    """
    cache_filename = f"dataset-{series_id}-{issue_name}.json"
    return cache_json_data(cache_filename, lambda: flygarmin_list_files(series_id, issue_name), force)

def get_unlock_data(access_token: str, series_id: int, issue_name: str, device_id: int, card_serial: int, force: bool = False) -> dict:
    """Obtain unlock code data with caching support.

    Args:
        access_token: Valid OAuth token for flygarmin API authentication
        series_id: Numeric identifier for the database series
        issue_name: String identifier for the specific issue (e.g., "2509")
        device_id: Target avionics device identifier
        card_serial: SD card volume serial number for unlock generation
        force: If True, ignore cache and fetch fresh data from API

    Returns:
        Dictionary containing unlock codes and activation data for the specified parameters
    """
    cache_filename = f"unlock-{series_id}-{issue_name}-{device_id}-{card_serial:08X}.json"
    return cache_json_data(cache_filename, lambda: flygarmin_unlock(access_token, series_id, issue_name, device_id, card_serial), force)

def get_default_device_id(aircraft_data: list) -> int:
    """Get the first available device ID from aircraft data.

    Args:
        aircraft_data: List of aircraft dictionaries from flygarmin API

    Returns:
        First device ID found

    Raises:
        ValueError: If no devices are found in aircraft data
    """
    for aircraft in aircraft_data:
        for device in aircraft['devices']:
            return device['id']
    raise ValueError("No devices found in aircraft data")

def get_system_serial(aircraft_data: list, device_id: int) -> int:
    """Get system serial number for a given device ID from aircraft data.

    Args:
        aircraft_data: List of aircraft dictionaries from flygarmin API
        device_id: Target device ID to find serial for

    Returns:
        Device serial number as integer

    Raises:
        ValueError: If device ID is not found in aircraft data
    """
    for aircraft in aircraft_data:
        for device in aircraft['devices']:
            if device['id'] == device_id:
                return device['serial']
    raise ValueError(f"Device ID {device_id} not found in aircraft data")

def list_series_details(series_id: int) -> None:
    """List detailed information about a specific series and exit.

    Args:
        series_id: The series ID to get details for
    """
    # Get series data from API
    series_data = flygarmin_list_series(series_id)

    # Print series header information
    print(f"Series ID: {series_data['id']}")
    print(f"Region: {series_data['region']['name']}")
    if 'nextExpectedAvdbAvailability' in series_data:
        next_expected = datetime.datetime.fromisoformat(series_data['nextExpectedAvdbAvailability'].replace('Z', '+00:00'))
        print(f"Next Expected Availability: {next_expected.strftime('%B %d, %Y')}")
    print()

    # Collect all issues with status
    all_issues = []

    # Add past issues
    for issue in series_data.get('pastIssues', []):
        all_issues.append((issue, 'Past'))

    # Add available issues
    for issue in series_data.get('availableIssues', []):
        all_issues.append((issue, 'Available'))

    # Add upcoming issues
    for issue in series_data.get('upcomingIssues', []):
        all_issues.append((issue, 'Upcoming'))

    # Sort by effectiveAt date
    all_issues.sort(key=lambda x: datetime.datetime.fromisoformat(x[0]['effectiveAt'].replace('Z', '+00:00')))

    # Print table header
    print(f"{'Issue':<8} {'Status':<10} {'Available At':<18} {'Effective At':<18} {'Invalid At':<18}")
    print("-" * 82)

    # Print each issue
    for issue, status in all_issues:
        available_at = datetime.datetime.fromisoformat(issue['availableAt'].replace('Z', '+00:00'))
        effective_at = datetime.datetime.fromisoformat(issue['effectiveAt'].replace('Z', '+00:00'))
        invalid_at = datetime.datetime.fromisoformat(issue['invalidAt'].replace('Z', '+00:00')) if issue['invalidAt'] else None

        available_str = available_at.strftime('%b %d, %Y')
        effective_str = effective_at.strftime('%b %d, %Y')
        invalid_str = invalid_at.strftime('%b %d, %Y') if invalid_at else 'N/A'

        print(f"{issue['name']:<8} {status:<10} {available_str:<18} {effective_str:<18} {invalid_str:<18}")

    sys.exit(0)

def list_aircraft_devices(aircraft_data: list) -> None:
    """List all aircraft and their devices in a human-readable format, then exit.

    Args:
        aircraft_data: List of aircraft dictionaries from flygarmin API.
    """
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

def download_file(url: str, expected_size: int, force: bool = False) -> pathlib.Path:
    """Download a file from the given URL with caching and size verification.

    Args:
        url: The complete URL to download from (e.g., "https://avdb.garmin.com/path/to/file.taw")
        expected_size: Expected file size in bytes for verification purposes
        force: If True, re-download file even if it already exists in cache

    Returns:
        Path object pointing to the downloaded/cached file location

    Raises:
        requests.HTTPError: If the HTTP request fails
        OSError: If file operations fail (permissions, disk space, etc.)
    """
    dest_path = get_cached_file_path_for_url(url)

    # Skip downloading if file already exists and force is False
    if not dest_path.exists() or force:
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

def copy_file(file_info: dict, output_path: pathlib.Path, force: bool = False) -> pathlib.Path:
    """Copy a file from cache to the output directory, preserving destination path.

    Args:
        file_info: Dictionary containing 'url' and 'destination' keys
        output_path: Base output directory path
        force: If True, copy unconditionally. If False, skip if destination exists and same size

    Returns:
        Path to the copied file
    """
    cached_path = get_cached_file_path_for_url(file_info['url'])
    output_file_path = output_path / pathlib.PurePosixPath(file_info['destination'])
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Only if destination is missing or has different size size
    if force or not output_file_path.exists() or cached_path.stat().st_size != output_file_path.stat().st_size:
        shutil.copy2(cached_path, output_file_path)

    return output_file_path

def installable_databases(aircraft_data: list, device_id: int) -> list[tuple[int, str]]:
    """Get all installable series/issue combinations for a specific device.

    Args:
        aircraft_data: List of aircraft dictionaries from flygarmin API
        device_id: Device ID to get databases for

    Returns:
        List of (series_id, issue_name) tuples for each valid dataset
    """
    databases = []

    # Generate all installable series/issue combinations for the specified device
    for aircraft in aircraft_data:
        for device in aircraft['devices']:
            if device_id == device['id']:
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

                            # Add to list
                            databases.append((series['id'], issue['name']))

    return databases

def main() -> None:
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download G3X data update and create SD card')

    # Informational
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-l', '--list-devices', action='store_true', help='List aircraft IDs and avionics device IDs for each aircraft')
    parser.add_argument('-i', '--series-info', type=int, metavar='SERIES_ID', help='Show detailed information about a specific series ID')

    # Data
    parser.add_argument('-c', '--check-crc', action='store_true', help='Perform CRC check during feature unlock generation (slow)')
    parser.add_argument('-I', '--include-series', action='append', nargs=2, metavar=('SERIES_ID', 'ISSUE_NAME'), help='Add specific series ID and issue name to output (can be specified multiple times, e.g., -I 2054 2509 -I 2056 25D4)')
    parser.add_argument('-W', '--include-taw', action='append', metavar='TAW_FILE', help='Include specific TAW file for extraction (can be specified multiple times, e.g., -W /path/to/file.taw -W /path/to/other.taw)')

    # Update SDCard
    parser.add_argument('-d', '--device-id', type=int, help='Specify avionics device ID for SD card programming. If not specified, use the first device in the first aircraft')
    parser.add_argument('-o', '--output', help='Specify output path (usually a mounted SD card path). If not specified, try to detect a SD card mount point')
    parser.add_argument('-s', '--sddevice', help=f"Specify SD card block device. This is required for building feat_unlk.dat and requires root privileges. Example: {get_platform_device_example()}")
    parser.add_argument('-N', '--vsn', type=lambda x: int(x, 16), help="Specify SD card volume serial number for building feat_unlk.dat. Does not require root privileges")

    # FlyGarmin authenitcation, query, and download overrides
    parser.add_argument('-T', '--access-token', help='Specify flygarmin access token')
    parser.add_argument('-L', '--force-login', action='store_true', help='Force a refresh of the flygarmin access token')
    parser.add_argument('-A', '--force-refresh-aircraft', action='store_true', help='Force a refresh of the aircraft data')
    parser.add_argument('-D', '--force-refresh-datasets', action='store_true', help='Force a refresh of the dataset data')
    parser.add_argument('-F', '--force-file-download', action='store_true', help='Force a re-download of the actual data files')
    parser.add_argument('-C', '--force-file-copy', action='store_true', help='Force copying files even if destination exists with same size')

    # Parse arguments
    args = parser.parse_args()

    # Verbose printing
    vprint = print if args.verbose else lambda *_: None

    # Try to detect a mounted SD card
    sd_card = detect_sd_card()

    # Get a path for the root output directory
    output_path = pathlib.Path(args.output or sd_card or "") if (args.output or sd_card) else None

    # Read the sdcard's serial number if it's not provided
    card_serial = args.vsn if args.vsn else read_vsn(args.sddevice) if args.sddevice else None

    # List series details and exit
    args.series_info and list_series_details(args.series_info) # type: ignore

    # Get access token either from the comand line, from the auth_json, or from flygarmin
    access_token = args.access_token or get_access_token(args.force_login)

    # Get aircraft data either from aircraft_json or from flygarmin
    aircraft_data = get_aircraft_data(access_token, args.force_refresh_aircraft)

    # List the aircraft and devices and exit
    args.list_devices and list_aircraft_devices(aircraft_data) # type: ignore

    # Select a device id, or use default aircraft/device
    device_id = args.device_id if args.device_id else get_default_device_id(aircraft_data)

    # Get system serial number from aircraft data
    system_serial = get_system_serial(aircraft_data, device_id)

    # List the installable databases
    databases = installable_databases(aircraft_data, device_id)

    # Add manually specified series/issue pairs
    if args.include_series:
        for series_id_str, issue_name in args.include_series:
            series_id = int(series_id_str)
            databases.append((series_id, issue_name))

    # File downloading

    for series_id, issue_name in databases:
        # Get the dataset descriptor for this series/issue
        files_data = get_dataset_files(series_id, issue_name, args.force_refresh_datasets)

        # Download all files (main and auxiliary)
        for file_info in files_data.get('mainFiles', []) + files_data.get('auxiliaryFiles', []):
            vprint(f"Obtaining {file_info['url']}")
            download_file(file_info['url'], file_info['fileSize'], args.force_file_download)

    # File copy / extraction

    if output_path:
        # Store list of data files / taw_regions
        features = []

        # Iterate through all installable series/issue combinations
        for series_id, issue_name in databases:
            vprint(f"Adding to SD card series {series_id}, issue {issue_name}")

            # Get the dataset descriptor for this series/issue
            files_data = get_dataset_files(series_id, issue_name)

            # Verfiy the main file is a TAW
            if files_data['issueType'] != "TAW":
                print(f"Warning: Unexpected issue type {files_data['issue_type']} for series {series_id}, issue {issue_name}", file=sys.stderr)
                continue

            # Extract main files
            for file_info in files_data.get('mainFiles', []):
                # Get destination path
                cached_path = get_cached_file_path_for_url(file_info['url'])

                # Extract each file to the root sdcard
                for taw_region_path, output_file_path in extract_taw(cached_path, output_path, skip_unknown_regions=True):
                    vprint(f"Extracted {cached_path} taw region {taw_region_path} to {output_file_path}")
                    if taw_region_path:
                        features.append((taw_region_path, output_file_path))

            # Copy auxiliary files
            for file_info in files_data.get('auxiliaryFiles', []):
                output_file_path = copy_file(file_info, output_path, args.force_file_copy)
                vprint(f"Copied {file_info['url']} to {output_file_path}")

            vprint(f"Finished adding series")

        # Process manually specified TAW files
        if args.include_taw:
            for taw_file_path in args.include_taw:
                vprint(f"Adding manual TAW file {taw_file_path}")
                taw_path = pathlib.Path(taw_file_path)

                if not taw_path.exists():
                    print(f"Warning: TAW file {taw_file_path} does not exist, skipping", file=sys.stderr)
                    continue

                # Extract each file to the root sdcard
                for taw_region_path, output_file_path in extract_taw(taw_path, output_path, skip_unknown_regions=True):
                    vprint(f"Extracted {taw_file_path} taw region {taw_region_path} to {output_file_path}")
                    if taw_region_path:
                        features.append((taw_region_path, output_file_path))

        # Activate features on the sdcard

        if card_serial:
            vprint(f"Creating SD card (s/n: {card_serial:08X}) at {output_path}, installable on device {device_id} (s/n: {system_serial})")

            # Activate all features
            for taw_region_path, output_file_path in features:
                vprint(f"Unlocking feature {taw_region_path}")
                update_feature_unlock(output_path, output_file_path, taw_region_path, card_serial, GARMIN_SECURITY_ID, system_serial, args.check_crc)

            vprint(f"Finished creating SD card")

if __name__ == "__main__":
    main()
