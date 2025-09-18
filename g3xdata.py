#!/usr/bin/env python3

import argparse
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
            service_url = data["serviceUrl"]
            service_ticket = data["serviceTicket"]
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
    return data["access_token"]

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

def get_aircraft(aircraft_data, aircraft_id):
    # Find the specified aircraft
    for a in aircraft_data:
        if str(a['id']) == aircraft_id:
            return a
    raise KeyError

def get_device(device_data, device_id):
    for d in device_data:
        if str(d['id']) == device_id:
            return d
    raise KeyError

def get_database(device, database_id):
    for db in device['avdbTypes']:
        if str(db['id']) == database_id:
            return db
    raise KeyError

def get_series(database, series_id):
    for s in database['series']:
        if str(s['id']) == series_id:
            return s
    raise KeyError

def get_issue(series, issue_name):
    for issue in series['installableIssues']:
        if issue['name'] == issue_name:
            return issue
    raise KeyError

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download G3X data update and create SD card')
    parser.add_argument('-T', '--access-token', default='garmin_auth.json', help='Specify file containing flygarmin access token')
    parser.add_argument('-X', '--aircraft-descriptor', help='Specify file containing an aircraft descriptor (for DEBUG only), to avoid request to flygarmin')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-A', '--list-aircraft', action='store_true', help='Output just the list of aircraft IDs')
    parser.add_argument('-a', '--aircraft-id', help='Specify aircraft ID')
    parser.add_argument('-D', '--list-devices', action='store_true', help='Output the list of device IDs for given aircraft')
    parser.add_argument('-d', '--device-id', help='Specify device ID')
    parser.add_argument('-B', '--list-databases', action='store_true', help='Output the list of database IDs for given aircraft and device')
    parser.add_argument('-b', '--database-id', help='Specify database ID')
    parser.add_argument('-S', '--list-series', action='store_true', help='Output the list of series IDs for given database')
    parser.add_argument('-s', '--series-id', help='Specify series ID')
    parser.add_argument('-I', '--list-issues', action='store_true', help='Output the list of installable issues for given series')
    parser.add_argument('-i', '--issue-name', help='Specify issue name')
    args = parser.parse_args()

    if args.aircraft_descriptor:
        # Use the provided aircraft descriptor file instead of making API calls
        with open(args.aircraft_descriptor, encoding="utf-8") as fd:
            aircraft_data = json.load(fd)
    else:
        # Query garmin for the aircraft data
        access_token = flygarmin_get_access_token(args.access_token)
        aircraft_data = flygarmin_list_aircraft(access_token)

    if args.list_aircraft:
        # Output just aircraft IDs
        for aircraft in aircraft_data:
            if args.verbose:
                print(f"{aircraft['id']}: {aircraft['name']}, {aircraft['year']} {aircraft['aircraftMakeName']} {aircraft['aircraftModelName']} S/N {aircraft['serial']}")
            else:
                print(aircraft['id'])

    elif args.aircraft_id:
        # Get individual aircraft info
        aircraft = get_aircraft(aircraft_data, args.aircraft_id)

        if args.list_devices:
            # List devices for the aircraft
            for device in aircraft["devices"]:
                if args.verbose:
                    print(f"{device['id']}: {device['name']} S/N {device['displaySerial']}")
                else:
                    print(device['id'])

        elif args.device_id:
            # Get individual device info
            device = get_device(aircraft["devices"], args.device_id)

            if args.list_databases:
                # List databases for the aircraft/device
                for database in device["avdbTypes"]:
                    if args.verbose:
                        print(f"{database['id']}: {database['name']}")
                    else:
                        print(f"{database['id']}")

            elif args.database_id:
                # Get individual database info
                database = get_database(device, args.database_id)

                if args.list_series:
                    # List series for the database
                    for series in database["series"]:
                        if args.verbose:
                            print(f"{series['id']}: {series['region']['name']}")
                        else:
                            print(series['id'])

                elif args.series_id:
                    # Get individual series info
                    series = get_series(database, args.series_id)

                    if args.list_issues:
                        # List installable issues for the series
                        for issue in series["installableIssues"]:
                            if args.verbose:
                                print(f"{issue['name']}: effective {issue['effectiveAt']}, invalid {issue['invalidAt']}")
                            else:
                                print(issue['name'])

                    elif args.issue_name:
                        # Get individual issue info
                        issue = get_issue(series, args.issue_name)
                        print(f"Issue: {issue['name']}")
                        print(f"Effective: {issue['effectiveAt']}")
                        print(f"Invalid: {issue['invalidAt']}")
                        print(f"Available: {issue['availableAt']}")

    elif args.series_id and args.issue_name:
        files = flygarmin_list_files(args.series_id, args.issue_name)
        print(json.dumps(files, indent=2))

    elif args.series_id:
        series = flygarmin_list_series(args.series_id)
        print(json.dumps(series, indent=2))

if __name__ == "__main__":
    main()