#!/usr/bin/env python3
"""
ivr_agi.py - Asterisk AGI script for verified self-service lookups.

Usage from the dialplan:
    AGI(ivr_agi.py,lookup,${CASE_ID},${PIN})
    AGI(ivr_agi.py,callback,${CASE_ID})

The script never speaks to the caller itself. It only sets channel variables,
and the dialplan decides which prompts to play. That keeps call-flow logic in
the dialplan and data access in one small, testable place.

Variables set on the channel:
    LOOKUP_RESULT      OK | NOT_FOUND | VERIFY_FAILED | ERROR
    REG_STATUS         REGISTERED | PENDING | NOT_REGISTERED   (when OK)
    NEXT_DIST_DATE     YYYYMMDD, or empty if none scheduled    (when OK)
    CASE_STATUS        RECEIVED | IN_PROGRESS | RESOLVED | NONE (when OK)
    CALLBACK_RESULT    OK | ERROR                              (callback action)

Only the Python standard library is used, so it runs on a stock Asterisk box.
"""

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE_URL = os.environ.get("IVR_API_BASE_URL", "http://127.0.0.1:8080")
CLIENT_ID = os.environ.get("IVR_API_CLIENT_ID", "ivr-demo")
CLIENT_SECRET = os.environ.get("IVR_API_CLIENT_SECRET", "change-me")
TIMEOUT = float(os.environ.get("IVR_API_TIMEOUT", "3"))
TOKEN_CACHE = os.environ.get("IVR_TOKEN_CACHE", "/tmp/ivr_agi_token.json")
LOG_FILE = os.environ.get("IVR_LOG_FILE", "/var/log/asterisk/ivr_agi.log")

log = logging.getLogger("ivr_agi")


def setup_logging():
    try:
        handler = logging.FileHandler(LOG_FILE)
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def mask(value, keep=2):
    """Mask identifiers in logs: 252612345678 -> **********78."""
    value = str(value or "")
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


# --------------------------------------------------------------------------
# AGI protocol
# --------------------------------------------------------------------------
class AGI:
    def __init__(self, stdin=sys.stdin, stdout=sys.stdout):
        self.stdin = stdin
        self.stdout = stdout
        self.env = {}
        self._read_env()

    def _read_env(self):
        for line in self.stdin:
            line = line.strip()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                self.env[key.strip()] = value.strip()

    def command(self, cmd):
        self.stdout.write(cmd + "\n")
        self.stdout.flush()
        return self.stdin.readline().strip()

    def set_variable(self, name, value):
        value = str(value).replace('"', "")
        return self.command('SET VARIABLE {} "{}"'.format(name, value))

    def verbose(self, message, level=3):
        message = str(message).replace('"', "")
        return self.command('VERBOSE "{}" {}'.format(message, level))


# --------------------------------------------------------------------------
# Backend API client (OAuth2 client-credentials)
# --------------------------------------------------------------------------
class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, base_url=API_BASE_URL, client_id=CLIENT_ID,
                 client_secret=CLIENT_SECRET, timeout=TIMEOUT,
                 token_cache=TOKEN_CACHE):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.token_cache = token_cache

    def _load_cached_token(self):
        try:
            with open(self.token_cache) as f:
                data = json.load(f)
            if data.get("expires_at", 0) > time.time() + 30:
                return data["access_token"]
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _fetch_token(self):
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        data = self._request("POST", "/oauth/token", body,
                             {"Content-Type": "application/x-www-form-urlencoded"})
        token = data["access_token"]
        try:
            with open(self.token_cache, "w") as f:
                json.dump({"access_token": token,
                           "expires_at": time.time() + int(data.get("expires_in", 300))}, f)
            os.chmod(self.token_cache, 0o600)
        except OSError:
            pass
        return token

    def _token(self, force=False):
        if not force:
            cached = self._load_cached_token()
            if cached:
                return cached
        return self._fetch_token()

    def _request(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.base_url + path, data=body,
                                     method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            e.payload = {}
            try:
                e.payload = json.loads(e.read().decode() or "{}")
            except ValueError:
                pass
            raise
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ApiError(str(e))

    def call(self, method, path, payload):
        """Authenticated JSON call. Refreshes the token once on 401."""
        body = json.dumps(payload).encode()
        for attempt in (1, 2):
            headers = {"Content-Type": "application/json",
                       "Authorization": "Bearer " + self._token(force=attempt == 2)}
            try:
                return 200, self._request(method, path, body, headers)
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 1:
                    continue
                return e.code, getattr(e, "payload", {})
        raise ApiError("unauthorized after token refresh")


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
def do_lookup(agi, api, case_id, pin):
    caller = agi.env.get("agi_callerid", "")
    uniqueid = agi.env.get("agi_uniqueid", "")

    if not case_id.isdigit() or not pin.isdigit():
        agi.set_variable("LOOKUP_RESULT", "NOT_FOUND")
        return "NOT_FOUND"

    try:
        status, data = api.call("POST", "/v1/self-service/lookup", {
            "case_id": case_id,
            "pin": pin,
            "msisdn": caller,
            "call_id": uniqueid,
        })
    except (ApiError, urllib.error.HTTPError) as e:
        log.error("call=%s lookup error: %s", uniqueid, e)
        agi.set_variable("LOOKUP_RESULT", "ERROR")
        return "ERROR"

    if status == 200:
        result = "OK"
        agi.set_variable("REG_STATUS", data.get("registration_status", "NOT_REGISTERED"))
        agi.set_variable("NEXT_DIST_DATE", data.get("next_distribution_date") or "")
        agi.set_variable("CASE_STATUS", data.get("case_status", "NONE"))
    elif status == 404:
        result = "NOT_FOUND"
    elif status == 403:
        result = "VERIFY_FAILED"
    else:
        result = "ERROR"

    agi.set_variable("LOOKUP_RESULT", result)
    log.info("call=%s caller=%s case=%s result=%s",
             uniqueid, mask(caller), mask(case_id), result)
    return result


def do_callback(agi, api, case_id=""):
    caller = agi.env.get("agi_callerid", "")
    uniqueid = agi.env.get("agi_uniqueid", "")
    try:
        status, _ = api.call("POST", "/v1/callbacks", {
            "msisdn": caller,
            "case_id": case_id or None,
            "language": agi.env.get("agi_language", "en"),
            "call_id": uniqueid,
        })
        result = "OK" if status in (200, 201) else "ERROR"
    except (ApiError, urllib.error.HTTPError) as e:
        log.error("call=%s callback error: %s", uniqueid, e)
        result = "ERROR"
    agi.set_variable("CALLBACK_RESULT", result)
    log.info("call=%s caller=%s callback=%s", uniqueid, mask(caller), result)
    return result


def main(argv, stdin=sys.stdin, stdout=sys.stdout, api=None):
    agi = AGI(stdin, stdout)
    api = api or ApiClient()
    action = argv[1] if len(argv) > 1 else ""

    if action == "lookup":
        case_id = argv[2] if len(argv) > 2 else ""
        pin = argv[3] if len(argv) > 3 else ""
        return do_lookup(agi, api, case_id, pin)
    if action == "callback":
        return do_callback(agi, api, argv[2] if len(argv) > 2 else "")

    agi.verbose("ivr_agi: unknown action " + action, 1)
    agi.set_variable("LOOKUP_RESULT", "ERROR")
    return "ERROR"


if __name__ == "__main__":
    setup_logging()
    try:
        main(sys.argv)
    except Exception:  # never leave the caller in dead air
        log.exception("unhandled error")
        sys.stdout.write('SET VARIABLE LOOKUP_RESULT "ERROR"\n')
        sys.stdout.flush()
