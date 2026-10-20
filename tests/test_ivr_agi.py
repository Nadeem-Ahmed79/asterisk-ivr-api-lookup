"""
End-to-end tests: real AGI protocol over fake stdin/stdout, against the mock API.

Run:  python3 -m unittest discover -s tests -v
"""

import io
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agi"))
sys.path.insert(0, os.path.join(ROOT, "mock-api"))

import ivr_agi  # noqa: E402
import server   # noqa: E402

GOOD_CALLER = "252610000001"


def agi_session(callerid, n_commands=10):
    """AGI env block followed by '200 result=1' replies to each command."""
    env = ("agi_request: ivr_agi.py\n"
           "agi_channel: PJSIP/trunk-00000001\n"
           "agi_language: so\n"
           "agi_uniqueid: 1761040000.1\n"
           "agi_callerid: {}\n\n").format(callerid)
    return io.StringIO(env + "200 result=1\n" * n_commands)


def channel_vars(stdout):
    out = {}
    for line in stdout.getvalue().splitlines():
        if line.startswith("SET VARIABLE "):
            name, value = line[len("SET VARIABLE "):].split(" ", 1)
            out[name] = value.strip('"')
    return out


class IvrAgiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        server.FAILED.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.api = ivr_agi.ApiClient(
            base_url="http://127.0.0.1:%d" % self.port,
            client_id="ivr-demo", client_secret="change-me",
            timeout=2, token_cache=os.path.join(self.tmp.name, "token.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_agi(self, argv, callerid=GOOD_CALLER, api=None):
        out = io.StringIO()
        result = ivr_agi.main(["ivr_agi.py"] + argv, agi_session(callerid), out, api or self.api)
        return result, channel_vars(out)

    def test_verified_lookup_returns_status(self):
        result, v = self.run_agi(["lookup", "100001", "4321"])
        self.assertEqual(result, "OK")
        self.assertEqual(v["REG_STATUS"], "REGISTERED")
        self.assertEqual(v["NEXT_DIST_DATE"], "20261105")
        self.assertEqual(v["CASE_STATUS"], "IN_PROGRESS")

    def test_wrong_pin_reveals_nothing(self):
        result, v = self.run_agi(["lookup", "100001", "0000"])
        self.assertEqual(result, "VERIFY_FAILED")
        self.assertNotIn("REG_STATUS", v)

    def test_unregistered_phone_number_fails_verification(self):
        result, v = self.run_agi(["lookup", "100001", "4321"], callerid="252619999999")
        self.assertEqual(result, "VERIFY_FAILED")
        self.assertNotIn("REG_STATUS", v)

    def test_unknown_case(self):
        result, _ = self.run_agi(["lookup", "999999", "1234"])
        self.assertEqual(result, "NOT_FOUND")

    def test_non_numeric_input_skips_api(self):
        result, _ = self.run_agi(["lookup", "", "1234"])
        self.assertEqual(result, "NOT_FOUND")

    def test_no_distribution_scheduled(self):
        result, v = self.run_agi(["lookup", "100002", "1111"], callerid="252610000002")
        self.assertEqual(result, "OK")
        self.assertEqual(v["NEXT_DIST_DATE"], "")

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.run_agi(["lookup", "100001", "0000"])
        result, _ = self.run_agi(["lookup", "100001", "4321"])
        self.assertEqual(result, "VERIFY_FAILED")

    def test_backend_down_gives_error_not_dead_air(self):
        api = ivr_agi.ApiClient(base_url="http://127.0.0.1:1", timeout=1,
                                token_cache=os.path.join(self.tmp.name, "t2.json"))
        result, v = self.run_agi(["lookup", "100001", "4321"], api=api)
        self.assertEqual(result, "ERROR")
        self.assertEqual(v["LOOKUP_RESULT"], "ERROR")

    def test_expired_cached_token_is_refreshed(self):
        with open(self.api.token_cache, "w") as f:
            f.write('{"access_token": "stale", "expires_at": 9999999999}')
        result, _ = self.run_agi(["lookup", "100001", "4321"])
        self.assertEqual(result, "OK")

    def test_callback_request(self):
        before = len(server.CALLBACKS)
        result, v = self.run_agi(["callback", "100001"])
        self.assertEqual(result, "OK")
        self.assertEqual(v["CALLBACK_RESULT"], "OK")
        self.assertEqual(len(server.CALLBACKS), before + 1)

    def test_mask(self):
        self.assertEqual(ivr_agi.mask("252610000001"), "**********01")


if __name__ == "__main__":
    unittest.main()
