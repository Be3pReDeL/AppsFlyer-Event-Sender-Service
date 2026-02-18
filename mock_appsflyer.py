#!/usr/bin/env python3
"""Mock AppsFlyer API server для локального тестирования."""

import json
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockAppsFlyerHandler(BaseHTTPRequestHandler):
    """Handler для mock AppsFlyer API."""

    def do_POST(self) -> None:
        """Handle POST requests to /inappevent/{app_id}."""
        # Parse path
        if not self.path.startswith("/inappevent/"):
            self.send_error(404, "Not Found")
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Validate authentication header
        auth = self.headers.get("authentication")
        if not auth:
            self.send_error(401, "Missing authentication header")
            return

        # Log request
        event_name = data.get("event_name", "unknown")
        appsflyer_id = data.get("appsflyer_id", "unknown")
        print(f"[MOCK AppsFlyer] Received event: {event_name}, device: {appsflyer_id}")
        print(f"[MOCK AppsFlyer] Payload: {json.dumps(data, indent=2)}")

        # Simulate different responses based on event data
        # 10% chance of 429 rate limit
        if random.random() < 0.1:
            print("[MOCK AppsFlyer] Simulating 429 rate limit")
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "2")
            self.end_headers()
            response = {"status": "error", "message": "Rate limit exceeded"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        # 5% chance of 500 server error
        if random.random() < 0.05:
            print("[MOCK AppsFlyer] Simulating 500 server error")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "error", "message": "Internal server error"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        # Success response
        print("[MOCK AppsFlyer] Sending success response")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        response = {
            "status": "success",
            "message": f"Event {event_name} recorded successfully",
        }
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """Override to customize logging."""
        # Only log errors
        if "error" in format.lower():
            print(f"[MOCK AppsFlyer] {format % args}")


def run_server(port: int = 8888) -> None:
    """Run mock AppsFlyer server."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, MockAppsFlyerHandler)
    print(f"[MOCK AppsFlyer] Starting mock server on port {port}")
    print(f"[MOCK AppsFlyer] Use: APPSFLYER_BASE_URL=http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[MOCK AppsFlyer] Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    run_server()
