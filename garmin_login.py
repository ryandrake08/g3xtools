#!/usr/bin/env python3
"""
Garmin OAuth Authentication Module

Handles OAuth authentication with Garmin's fly.garmin.com service for accessing
aviation database APIs. Provides both programmatic access for other modules
and standalone command-line functionality for testing and token management.

This module implements the complete OAuth flow:
1. Starts a local HTTP server to handle OAuth callbacks
2. Opens a browser to Garmin's SSO login page
3. Captures the service ticket from the callback
4. Exchanges the service ticket for an access token
5. Caches the token data for reuse

Features:
- Browser-based OAuth login with local callback server
- Automatic token caching in JSON files
- Standalone CLI for testing and token extraction

Example usage:
    # As a module
    from garmin_login import flygarmin_get_access_token
    token = flygarmin_get_access_token()

    # Standalone
    python3 garmin_login.py --dump-auth-json auth.json
"""

import http.server
import json
import shutil
import socketserver
import urllib.parse
import webbrowser
from http import HTTPStatus
from pathlib import Path
from typing import Any

import requests

# Public API
__all__ = [
    'flygarmin_login',
]

SSO_CLIENT_ID = "FLY_GARMIN_DESKTOP"
OAUTH_TOKEN_URL = "https://services.garmin.com/api/oauth/token"

class GarminHandler(http.server.BaseHTTPRequestHandler):
    def handle_credentials(self, auth: dict[str, str]) -> None:
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
            try:
                data = json.loads(content)
                service_url = data['serviceUrl']
                service_ticket = data['serviceTicket']
            except (json.JSONDecodeError, KeyError) as e:
                raise ValueError(f"Invalid OAuth callback data: {e}") from e
            print(f"Service URL: {service_url}")
            print(f"Service ticket: {service_ticket}")
            print("Received ticket. Requesting access token")

            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

            try:
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
            except requests.RequestException as e:
                raise OSError(f"Failed to obtain access token: {e}") from e

        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

def flygarmin_login() -> dict[str, Any]:
    """Perform OAuth login flow and return json containing credentials and other data."""
    data: dict[str, Any] = {}

    # Overridden from GarminHandler to set our local variable
    class Handler(GarminHandler):
        def handle_credentials(self, auth: dict[str, Any]) -> None:
            nonlocal data
            data = auth
            print("Done retrieving access token data")

    # Host a web server on localhost to perform oauth login
    with socketserver.TCPServer(("localhost", 0), Handler) as httpd:
        host, port = httpd.server_address[:2]
        url = f"http://{host}:{port}"
        print(f"Serving at {url}")
        webbrowser.open(url)
        while not data:
            httpd.handle_request()

    # Return the authentication record
    return data

def main() -> None:
    # Obtain the access token and print it to stdout
    access_token = flygarmin_login()
    print(access_token)

if __name__ == "__main__":
    main()
