#!/usr/bin/env python3
"""
Mock backend API for local testing of the IVR (standard library only).

Endpoints:
    POST /oauth/token               OAuth2 client-credentials token
    POST /v1/self-service/lookup    verify caller and return status
    POST /v1/callbacks              log a callback request

Run:  python3 mock-api/server.py   (listens on 127.0.0.1:8080)
"""

import json
import os
import secrets
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLIENT_ID = os.environ.get("IVR_API_CLIENT_ID", "ivr-demo")
CLIENT_SECRET = os.environ.get("IVR_API_CLIENT_SECRET", "change-me")
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data.json")

TOKENS = {}      # token -> expiry
CALLBACKS = []   # in-memory callback queue
FAILED = {}      # case_id -> failed verification count


def load_cases():
    with open(DATA_FILE) as f:
        return {c["case_id"]: c for c in json.load(f)["cases"]}


class Handler(BaseHTTPRequestHandler):
    cases = load_cases()

    def log_message(self, fmt, *args):
        sys.stderr.write("mock-api: " + fmt % args + "\n")

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode()

    def _authorized(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        return TOKENS.get(token, 0) > time.time()

    def do_POST(self):
        if self.path == "/oauth/token":
            form = urllib.parse.parse_qs(self._body())
            if (form.get("grant_type") == ["client_credentials"]
                    and form.get("client_id") == [CLIENT_ID]
                    and form.get("client_secret") == [CLIENT_SECRET]):
                token = secrets.token_urlsafe(24)
                TOKENS[token] = time.time() + 300
                return self._send(200, {"access_token": token,
                                        "token_type": "Bearer", "expires_in": 300})
            return self._send(401, {"error": "invalid_client"})

        if not self._authorized():
            return self._send(401, {"error": "invalid_token"})

        try:
            data = json.loads(self._body() or "{}")
        except ValueError:
            return self._send(400, {"error": "bad_json"})

        if self.path == "/v1/self-service/lookup":
            case = self.cases.get(str(data.get("case_id", "")))
            if not case:
                return self._send(404, {"error": "not_found"})
            case_id = case["case_id"]
            if FAILED.get(case_id, 0) >= 5:
                return self._send(403, {"error": "locked"})
            # Verification: PIN must match AND call must come from a registered number.
            if data.get("pin") != case["pin"] or data.get("msisdn") not in case["msisdns"]:
                FAILED[case_id] = FAILED.get(case_id, 0) + 1
                return self._send(403, {"error": "verification_failed"})
            FAILED.pop(case_id, None)
            return self._send(200, {
                "registration_status": case["registration_status"],
                "next_distribution_date": case.get("next_distribution_date"),
                "case_status": case.get("case_status", "NONE"),
            })

        if self.path == "/v1/callbacks":
            CALLBACKS.append({**data, "requested_at": int(time.time())})
            return self._send(201, {"queued": len(CALLBACKS)})

        return self._send(404, {"error": "unknown_endpoint"})


def make_server(host="127.0.0.1", port=8080):
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    port = int(os.environ.get("MOCK_API_PORT", "8080"))
    print("Mock API listening on http://127.0.0.1:%d" % port)
    make_server(port=port).serve_forever()
