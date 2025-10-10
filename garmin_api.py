#!/usr/bin/env python3
"""
Garmin Aviation Database REST API Client

Provides a clean interface to Garmin's fly.garmin.com REST APIs for accessing
aviation database information. This module handles all HTTP requests and
response parsing for aircraft, device, series, and file operations.

API Functions:
- flygarmin_list_aircraft(): Get user's registered aircraft with device info
- flygarmin_list_series(): Get information about specific database series
- flygarmin_list_files(): Get downloadable files for series/issue combinations
- flygarmin_unlock(): Unlock files for download to specific devices

The module maintains a requests session with proper headers and handles
authentication via Bearer tokens obtained from the garmin_login module.

Features:
- Automatic HTTP error handling with raise_for_status()
- JSON response parsing
- Standalone CLI for testing individual API endpoints

Example usage:
    # As a module
    from garmin_api import flygarmin_list_aircraft
    aircraft = flygarmin_list_aircraft(access_token)

    # Standalone testing
    python3 garmin_api.py -t aircraft
    python3 garmin_api.py -t series --series-id 12345
"""

import argparse
import json
import sys

import requests

# Public API
__all__ = [
    'flygarmin_list_aircraft',
    'flygarmin_list_series',
    'flygarmin_list_files',
    'flygarmin_unlock',
]

API_PREFIX = "https://fly.garmin.com/fly-garmin/api"
API_TIMEOUT = 30  # seconds

session = requests.Session()
del session.headers['User-Agent']  # Garmin API accepts requests without User-Agent

def flygarmin_list_aircraft(access_token: str) -> list:
    """
    List all aircraft registered to the user.

    Args:
        access_token: OAuth bearer token from flygarmin_login()

    Returns:
        List of aircraft dictionaries containing device and database information

    Raises:
        requests.HTTPError: If API request fails
        ValueError: If response is not JSON
    """
    print(f"[flygarmin] Listing all aircraft for access token {access_token}")
    resp = session.get(
        f"{API_PREFIX}/aircraft/",
        params={
            "withAvdbs": "true",
            "withJeppImported": "true",
            "withSharedAircraft": "true",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    if 'application/json' not in resp.headers.get('Content-Type', ''):
        raise ValueError(f"Expected JSON response, got Content-Type: {resp.headers.get('Content-Type')}")
    result: list = resp.json()
    return result

def flygarmin_list_series(series_id: int) -> dict:
    """
    Get information about a specific database series.

    Args:
        series_id: Numeric series identifier

    Returns:
        Dictionary containing series metadata (region, name, etc.)

    Raises:
        requests.HTTPError: If API request fails
        ValueError: If response is not JSON
    """
    print(f"[flygarmin] Listing information for series {series_id}")
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/",
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    if 'application/json' not in resp.headers.get('Content-Type', ''):
        raise ValueError(f"Expected JSON response, got Content-Type: {resp.headers.get('Content-Type')}")
    result: dict = resp.json()
    return result

def flygarmin_list_files(series_id: int, issue_name: str) -> dict:
    """
    Get list of downloadable files for a specific series and issue.

    Args:
        series_id: Numeric series identifier
        issue_name: Issue name (e.g., "2024-01")

    Returns:
        Dictionary containing file URLs and metadata

    Raises:
        requests.HTTPError: If API request fails
        ValueError: If response is not JSON
    """
    print(f"[flygarmin] Listing files for series {series_id}, issue {issue_name}")
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/{issue_name}/files/",
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    if 'application/json' not in resp.headers.get('Content-Type', ''):
        raise ValueError(f"Expected JSON response, got Content-Type: {resp.headers.get('Content-Type')}")
    result: dict = resp.json()
    return result

def flygarmin_unlock(access_token: str, series_id: int, issue_name: str, device_id: int, card_serial: int) -> dict:
    """
    Get unlock codes for downloading files to a specific device and SD card.

    Args:
        access_token: OAuth bearer token from flygarmin_login()
        series_id: Numeric series identifier
        issue_name: Issue name (e.g., "2024-01")
        device_id: Device ID from aircraft data
        card_serial: SD card volume serial number (hex)

    Returns:
        Dictionary containing unlock URLs and codes

    Raises:
        requests.HTTPError: If API request fails
        ValueError: If response is not JSON
    """
    print(f"[flygarmin] Getting unlock code for series {series_id}, issue {issue_name} for installtaion on device {device_id}, sdcard {card_serial:08X}, using access token {access_token}")
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/{issue_name}/unlock/",
        params={
            "deviceIDs": device_id,
            "cardSerial": card_serial,
        },
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    if 'application/json' not in resp.headers.get('Content-Type', ''):
        raise ValueError(f"Expected JSON response, got Content-Type: {resp.headers.get('Content-Type')}")
    result: dict = resp.json()
    return result

def main() -> None:
    """Simple test interface for the Garmin API functions."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Garmin API functions')
    parser.add_argument('-T', '--access-token', help='Specify flygarmin access token')
    parser.add_argument('-t', '--test', choices=['aircraft', 'series', 'files', 'unlock'], help='Test a specific API function')
    parser.add_argument('--series-id', type=int, help='Series ID for testing')
    parser.add_argument('--issue-name', help='Issue name for testing')
    parser.add_argument('--device-id', type=int, help='Device ID for testing')
    parser.add_argument('--card-serial', type=int, help='Card serial for testing')
    args = parser.parse_args()

    # Get access token
    access_token = args.access_token

    if args.test == 'aircraft':
        aircraft_result = flygarmin_list_aircraft(access_token)
        print(json.dumps(aircraft_result, indent=2))
    elif args.test == 'series':
        if not args.series_id:
            print("Error: --series-id required for series test", file=sys.stderr)
            sys.exit(1)
        series_result = flygarmin_list_series(args.series_id)
        print(json.dumps(series_result, indent=2))
    elif args.test == 'files':
        if not args.series_id or not args.issue_name:
            print("Error: --series-id and --issue-name required for files test", file=sys.stderr)
            sys.exit(1)
        files_result = flygarmin_list_files(args.series_id, args.issue_name)
        print(json.dumps(files_result, indent=2))
    elif args.test == 'unlock':
        if not all([args.series_id, args.issue_name, args.device_id, args.card_serial]):
            print("Error: --series-id, --issue-name, --device-id, and --card-serial required for unlock test", file=sys.stderr)
            sys.exit(1)
        unlock_result = flygarmin_unlock(access_token, args.series_id, args.issue_name, args.device_id, args.card_serial)
        print(json.dumps(unlock_result, indent=2))
    elif access_token:
        print("Access token obtained successfully:", access_token)
    else:
        print("Failed to obtain access token")

if __name__ == "__main__":
    main()
