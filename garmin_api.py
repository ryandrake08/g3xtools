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
import requests

API_PREFIX = "https://fly.garmin.com/fly-garmin/api"

session = requests.Session()
session.headers['User-Agent'] = None  # type: ignore

def flygarmin_list_aircraft(access_token: str) -> list:
    """List all aircraft registered to the user."""
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
    )
    resp.raise_for_status()
    return resp.json()

def flygarmin_list_series(series_id: int) -> dict:
    """Get information about a specific series."""
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/",
    )
    resp.raise_for_status()
    return resp.json()

def flygarmin_list_files(series_id: int, issue_name: str) -> dict:
    """Get list of files for a specific series and issue."""
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/{issue_name}/files/",
    )
    resp.raise_for_status()
    return resp.json()

def flygarmin_unlock(access_token: str, series_id: int, issue_name: str, device_id: int, card_serial: int) -> dict:
    """Unlock files for download for a specific device and card."""
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/{issue_name}/unlock/",
        params={
            "deviceIDs": device_id,
            "cardSerial": card_serial,
        },
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )
    resp.raise_for_status()
    return resp.json()

def main():
    """Simple test interface for the Garmin API functions."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Garmin API functions')
    parser.add_argument('-T', '--access-token', help='Specify flygarmin access token')
    parser.add_argument('-t', '--test', choices=['aircraft', 'series', 'files', 'unlock'], help='Test a specific API function')
    parser.add_argument('--series-id', type=int, help='Series ID for testing')
    parser.add_argument('--issue-name', help='Issue name for testing')
    parser.add_argument('--device-id', type=int, help='Device ID for testing')
    parser.add_argument('--card-serial', type=int, help='Card serial for testing')
    # Development/debug arguments
    parser.add_argument('--auth-json', help='Authentication JSON file')
    parser.add_argument('--dump-auth-json', help='Dump authentication JSON to file')
    args = parser.parse_args()

    from garmin_login import flygarmin_get_access_token

    # Get access token
    access_token = args.access_token or flygarmin_get_access_token(args.auth_json, args.dump_auth_json)

    if args.test == 'aircraft':
        result = flygarmin_list_aircraft(access_token)
        print(json.dumps(result, indent=2))
    elif args.test == 'series':
        if not args.series_id:
            print("Error: --series-id required for series test")
            return
        result = flygarmin_list_series(args.series_id)
        print(json.dumps(result, indent=2))
    elif args.test == 'files':
        if not args.series_id or not args.issue_name:
            print("Error: --series-id and --issue-name required for files test")
            return
        result = flygarmin_list_files(args.series_id, args.issue_name)
        print(json.dumps(result, indent=2))
    elif args.test == 'unlock':
        if not all([args.series_id, args.issue_name, args.device_id, args.card_serial]):
            print("Error: --series-id, --issue-name, --device-id, and --card-serial required for unlock test")
            return
        result = flygarmin_unlock(access_token, args.series_id, args.issue_name, args.device_id, args.card_serial)
        print(json.dumps(result, indent=2))
    else:
        print("Access token obtained successfully:", access_token)

if __name__ == "__main__":
    main()