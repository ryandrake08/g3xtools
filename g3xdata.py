#!/usr/bin/env python3

import argparse
from datetime import datetime
import http.server
from http import HTTPStatus
import json
import requests
import shutil
import socketserver
import urllib.parse
import webbrowser
from pathlib import Path

SSO_CLIENT_ID = "FLY_GARMIN_DESKTOP"
OAUTH_TOKEN_URL = "https://services.garmin.com/api/oauth/token"
API_PREFIX = "https://fly.garmin.com/fly-garmin/api"

class GarminHandler(http.server.BaseHTTPRequestHandler):
    def handle_credentials(self, auth: dict[str, str]):
        ...

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path, scheme="http", allow_fragments=False).path

        if path == "/":
            sso_html = Path(__file__).parent / "flygarmin" / "index.html"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(sso_html.stat().st_size))
            self.end_headers()
            with open(sso_html, "rb") as fd:
                shutil.copyfileobj(fd, self.wfile)

        elif path == "/sso.js":
            sso_js = Path(__file__).parent / "flygarmin" / "sso.js"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(sso_js.stat().st_size))
            self.end_headers()
            with open(sso_js, "rb") as fd:
                shutil.copyfileobj(fd, self.wfile)

        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path, scheme="http", allow_fragments=False).path

        if path == "/login":
            length = int(self.headers.get("Content-Length", "0"))
            content = self.rfile.read(length)
            data = json.loads(content)
            service_url = data['serviceUrl']
            service_ticket = data['serviceTicket']
            print(f"Service URL: {service_url}")
            print(f"Service ticket: {service_ticket}")
            print("Received ticket. Requesting access token")

            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

            resp = requests.post(
                OAUTH_TOKEN_URL,
                data={
                    'grant_type': 'service_ticket',
                    'client_id': SSO_CLIENT_ID,
                    'service_url': service_url,
                    'service_ticket': service_ticket,
                },
                timeout=5,
            )
            resp.raise_for_status()
            print("Received access token")
            self.handle_credentials(resp.json())

        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

def flygarmin_login(auth_filename) -> dict[str, str]:
    data: dict[str, str] | None = None

    # Overridden from GarminHandler to set our local variable
    class Handler(GarminHandler):
        def handle_credentials(self, auth):
            nonlocal data
            data = auth
            print(f"Done retrieving access token data")

    # Host a web server on localhost to perform oauth login
    with socketserver.TCPServer(("localhost", 0), Handler) as httpd:
        host, port = httpd.server_address[:2]
        url = f"http://{host}:{port}"
        print(f"Serving at {url}")
        webbrowser.open(url)
        while not data:
            httpd.handle_request()

    # Save the token data for later
    with open(auth_filename, "w", encoding="utf-8") as fd:
        json.dump(data, fd)

    return data

def flygarmin_get_access_token(auth_filename):
    try:
        # First look for specified file
        with open(auth_filename, encoding="utf-8") as fd:
            data = json.load(fd)
    except FileNotFoundError:
        # If not found, attempt to login to produce file
        data = flygarmin_login(auth_filename)

    # At this point, we should have the token data
    return data['access_token']

session = requests.Session()
session.headers['User-Agent'] = None  # type: ignore

def flygarmin_list_aircraft(access_token) -> list:
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
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/",
    )
    resp.raise_for_status()
    return resp.json()

def flygarmin_list_files(series_id: int, issue_name: str) -> dict:
    resp = session.get(
        f"{API_PREFIX}/avdb-series/{series_id}/{issue_name}/files/",
    )
    resp.raise_for_status()
    return resp.json()

def flygarmin_unlock(access_token: str, series_id: int, issue_name: str, device_id: int, card_serial: int) -> dict:
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

def download_file(url, dest_path, expected_size=None, verbose=False):
    """Download a file with conditional headers if it already exists."""
    dest_file = Path(dest_path)
    headers = {}

    # Check if file already exists and set If-Modified-Since header
    if dest_file.exists():
        # Get the modification time and format it for HTTP header
        mtime = dest_file.stat().st_mtime
        if_modified_since = datetime.fromtimestamp(mtime).strftime('%a, %d %b %Y %H:%M:%S GMT')
        headers['If-Modified-Since'] = if_modified_since

        if verbose:
            print(f"    File exists, checking if modified since {if_modified_since}")

    # Create parent directories if they don't exist
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    try:
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
        with open(dest_file, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Verify file size if expected_size is provided
        actual_size = dest_file.stat().st_size
        if expected_size and actual_size != expected_size:
            print(f"    Warning: Expected {expected_size} bytes, got {actual_size} bytes")

        return True  # File downloaded

    except requests.RequestException as e:
        print(f"    Error downloading {url}: {e}")
        return False

def download_files_in(files_list, cache_path, verbose=False):
    """Download a list of files from files_data structure."""
    cache_root = Path(cache_path)

    for file_info in files_list:
        url = file_info['url']
        destination = file_info.get('destination')
        file_size = file_info.get('fileSize')

        if destination:
            dest_path = cache_root / destination
            if verbose:
                print(f"  Destination filename is: {destination}")
        else:
            # Extract filename from URL and place in root cache_path
            filename = Path(urllib.parse.urlparse(url).path).name
            dest_path = cache_root / filename
            if verbose:
                print(f"  No destination specified, using: {filename}")

        download_file(url, str(dest_path), file_size, verbose)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download G3X data update and create SD card')
    parser.add_argument('-T', '--access-token', default='garmin_auth.json', help='Specify file containing flygarmin access token')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    # List aircraft and devices
    parser.add_argument('-l', '--list', action='store_true', help='List aircraft IDs and device IDs for each aircraft')
    # Download
    parser.add_argument('-a', '--aircraft-id', help='Specify aircraft ID')
    parser.add_argument('-d', '--device-id', help='Specify device ID')
    parser.add_argument('-c', '--cache-path', default='cache', help='Specify root path to cache downloaded files')
    # Get information about series
    parser.add_argument('-s', '--series-info', help='Get information about a particular series')
    # Development/debug arguments
    parser.add_argument('--dump-aircraft-descriptor', help='Output a file containing an aircraft descriptor (for DEBUG only) and then exit')
    parser.add_argument('--aircraft-descriptor', help='Specify file containing an aircraft descriptor (for DEBUG only), to avoid request to flygarmin')
    args = parser.parse_args()

    if args.series_info:
        # Print series info and exit
        try:
            series = flygarmin_list_series(args.series_info)
            print(json.dumps(series, indent=2))
        except Exception as e:
            print(f"Error getting series info: {e}")
        return

    if args.aircraft_descriptor:
        # Use the provided aircraft descriptor file instead of making API calls
        with open(args.aircraft_descriptor, encoding="utf-8") as fd:
            aircraft_data = json.load(fd)
    else:
        # Query garmin for the aircraft data
        try:
            access_token = flygarmin_get_access_token(args.access_token)
            aircraft_data = flygarmin_list_aircraft(access_token)
        except Exception as e:
            print(f"Error getting aircraft data: {e}")
            return

    if args.dump_aircraft_descriptor:
        # Print the aircraft descriptor and exit
        print(json.dumps(aircraft_data, indent=2))
        return

    if args.list:
        # List the aircraft and devices and exit
        for aircraft in aircraft_data:
            device_ids = [str(device['id']) for device in aircraft['devices']]
            print(f"Aircraft: {aircraft['id']}: Devices: {', '.join(device_ids)}")
        return

    if args.aircraft_id and args.device_id and args.cache_path:
        # Download the current installable series/issue of all avdb types
        aircraft = next((a for a in aircraft_data if str(a['id']) == args.aircraft_id), None)
        if aircraft is None:
            raise KeyError

        device = next((d for d in aircraft['devices'] if str(d['id']) == args.device_id), None)
        if device is None:
            raise KeyError

        # Collect all series/issue combinations
        series_issue_list = []
        for avdb in device['avdbTypes']:
            for series in avdb['series']:
                for issue in series['installableIssues']:
                    # Parse the date strings and check if issue is currently valid
                    effective_at = datetime.fromisoformat(issue['effectiveAt'].replace('Z', '+00:00'))
                    invalid_at = None if issue['invalidAt'] is None else datetime.fromisoformat(issue['invalidAt'].replace('Z', '+00:00'))
                    now = datetime.now().astimezone()

                    # Only include if today's time is >= effectiveAt and < invalidAt (or invalidAt is None)
                    if effective_at <= now and (invalid_at is None or now < invalid_at):
                        series_issue_list.append((avdb['name'], series['region']['name'], series['id'], issue['name']))

        # Download files for each series/issue combination
        for avdb_name, series_region_name, series_id, issue_name in series_issue_list:
            if args.verbose:
                print(f"Processing {avdb_name}: {series_region_name}, Issue: {issue_name}")

            # Get the file list for this series/issue
            try:
                files_data = flygarmin_list_files(series_id, issue_name)
            except Exception as e:
                print(f"  Error getting file list for series {series_id}, issue {issue_name}: {e}")
                continue

            # Download main files
            if 'mainFiles' in files_data:
                download_files_in(files_data['mainFiles'], args.cache_path, args.verbose)

            # Download auxiliary files
            if 'auxiliaryFiles' in files_data:
                download_files_in(files_data['auxiliaryFiles'], args.cache_path, args.verbose)

        return

if __name__ == "__main__":
    main()