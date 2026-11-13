"""HM-1: the Settings page and its one write path, POST /settings (guard tests through the real server).

Must reject: a LAN bind, a missing or foreign Origin, a missing or wrong form token, a non-form body, an oversized body,
an unknown key, an empty value, other methods and other paths. Must accept: a valid POST on a loopback bind, which runs
the real `bin/factory config` against a throwaway FACTORY_HOME, records the value and a `config set` event.
"""
import contextlib
import http.client
import io
import re
import sys
import threading
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from harness import FactoryTestCase  # noqa: E402
from test_web_server import ServerCase, get  # noqa: E402
from web import server  # noqa: E402
from web.views import settings  # noqa: E402

KEY = "worktree_reuse"
TOKEN_RE = re.compile(rb'name="token" value="([^"]+)"')


def post(httpd, path, fields=None, *, origin="auto", token=None, ctype=server.FORM_TYPE, body=None, method="POST"):
    port = httpd.server_address[1]
    host = f"127.0.0.1:{port}"
    data = body if body is not None else urlencode({**({"token": token} if token is not None else {}),
                                                    **(fields or {})}).encode()
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        c.putheader("Host", host)
        if origin:
            c.putheader("Origin", f"http://{host}" if origin == "auto" else origin)
        if ctype:
            c.putheader("Content-Type", ctype)
        c.putheader("Content-Length", str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        c.close()


class SettingsPage(ServerCase):
    def post(self, *a, **k):
        with contextlib.redirect_stderr(io.StringIO()):
            return post(self.httpd, *a, **k)

    def token(self):
        st, _, body = self.get("/settings")
        self.assertEqual(st, 200)
        return TOKEN_RE.search(body).group(1).decode()

    def test_sidebar_links_settings_and_page_lists_worktree_group_first(self):
        st, h, body = self.get("/settings")
        self.assertEqual(st, 200)
        self.assertIn(b'href="/settings"', self.get("/goals")[2])
        text = body.decode()
        self.assertLess(text.index("Worktrees"), text.index("worktree_pool_max"))
        self.assertLess(text.index(KEY), text.index("worktree_pool_max"))
        # the page with forms may post to itself, with a same-origin referrer policy; other pages keep 'none'
        self.assertIn("form-action 'self'", h["Content-Security-Policy"])
        self.assertEqual(h["Referrer-Policy"], server.REFERRER_FORMS)
        _, h2, _ = self.get("/goals")
        self.assertIn("form-action 'none'", h2["Content-Security-Policy"])
        self.assertEqual(h2["Referrer-Policy"], server.REFERRER)

    def test_loopback_page_has_forms_lan_page_has_commands_only(self):
        body = self.get("/settings")[2]
        self.assertIn(b'<form method="post" action="/settings"', body)
        self.httpd.app.loopback = False   # what a LAN bind sets (is_loopback of a private address is False)
        body = self.get("/settings")[2]
        self.assertNotIn(b"<form", body)
        self.assertIn(f"factory config {KEY} 1".encode(), body)
        self.assertFalse(server.is_loopback("192.168.1.10"))
        self.assertTrue(server.is_loopback("127.0.0.1"))

    def test_api_json_never_carries_the_form_token(self):
        tok = self.token()
        st, _, body = self.get("/api/settings.json")
        self.assertEqual(st, 200)
        self.assertNotIn(tok.encode(), body)

    # ── must reject ──

    def test_rejects_on_lan_bind(self):
        tok = self.token()
        self.httpd.app.loopback = False
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"}, token=tok)[0], 403)

    def test_rejects_without_or_with_foreign_origin(self):
        tok = self.token()
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"}, token=tok, origin=None)[0], 403)
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"}, token=tok, origin="null")[0], 403)
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"}, token=tok,
                                   origin="http://evil.example")[0], 403)

    def test_rejects_missing_or_wrong_token(self):
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"})[0], 403)
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"}, token="x" * 43)[0], 403)

    def test_rejects_bad_body(self):
        tok = self.token()
        self.assertEqual(self.post("/settings", {"key": KEY, "value": "1"}, token=tok, ctype="application/json")[0], 400)
        big = urlencode({"token": tok, "key": KEY, "value": "1", "pad": "x" * server.MAX_FORM_BYTES}).encode()
        self.assertEqual(self.post("/settings", body=big)[0], 413)

    def test_rejects_unknown_key_and_empty_value(self):
        tok = self.token()
        self.assertEqual(self.post("/settings", {"key": "serve_bind", "value": "0.0.0.0"}, token=tok)[0], 400)
        self.assertEqual(self.post("/settings", {"key": KEY, "value": " "}, token=tok)[0], 400)

    def test_other_methods_and_paths_stay_405(self):
        tok = self.token()
        for method in ("PUT", "DELETE", "PATCH"):
            with self.subTest(method):
                st, h, _ = self.post("/settings", {"key": KEY, "value": "1"}, token=tok, method=method)
                self.assertEqual((st, h["Allow"]), (405, "GET, HEAD"))
        self.assertEqual(self.post("/goals", {"key": KEY, "value": "1"}, token=tok)[0], 405)

    def test_nothing_runs_when_a_check_fails(self):
        calls = []
        orig = settings.apply_change
        settings.apply_change = lambda *a, **k: calls.append(a) or (True, "")
        self.addCleanup(setattr, settings, "apply_change", orig)
        self.post("/settings", {"key": KEY, "value": "1"}, token="wrong")
        self.post("/settings", {"key": "serve_bind", "value": "1"}, token=self.token())
        self.assertEqual(calls, [])


class SettingsWrite(FactoryTestCase):
    """Accept path through the real CLI: the server stays read-only, `bin/factory config` does the write."""

    def setUp(self):
        super().setUp()
        e = self.env
        self.httpd = server.make_server(e.db_path, "127.0.0.1", 0, (), tokens=lambda: {"rows": []},
                                        defaults={"worktree_reuse": "0", "worktree_pool_max": "2"}, factory_home=e.home_dir)
        self.httpd.app.config_env = e.env()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def page(self, path="/settings"):
        with contextlib.redirect_stderr(io.StringIO()):
            return get(self.httpd, path)

    def submit(self, key, value):
        tok = TOKEN_RE.search(self.page()[2]).group(1).decode()
        with contextlib.redirect_stderr(io.StringIO()):
            return post(self.httpd, "/settings", {"key": key, "value": value}, token=tok)

    def value(self, key):
        rows = self.env.sql("SELECT value FROM config WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def test_valid_change_is_written_by_the_cli_and_logged(self):
        st, h, _ = self.submit(KEY, "1")
        self.assertEqual(st, 303, h)
        loc = urlsplit(h["Location"])
        self.assertEqual((loc.path, parse_qs(loc.query)), ("/settings", {settings.Q_SAVED: [KEY]}))
        self.assertEqual(self.value(KEY), "1")
        ev = self.env.sql("SELECT entity, entity_id, action, detail FROM events WHERE entity='config' AND entity_id=?", (KEY,))
        self.assertEqual([(r["action"], r["detail"]) for r in ev], [("set", "1")])
        body = self.page(h["Location"].split("#")[0])[2].decode()
        self.assertIn("Saved.", body)
        self.assertRegex(body, r'class="set-value">On<')

    def test_value_the_cli_refuses_is_reported_and_not_written(self):
        before = self.value("worktree_pool_max")
        st, h, _ = self.submit("worktree_pool_max", "999")
        self.assertEqual(st, 303)
        q = parse_qs(urlsplit(h["Location"]).query)
        self.assertEqual(q[settings.Q_ERROR], ["worktree_pool_max"])
        self.assertTrue(q[settings.Q_MSG][0])
        self.assertEqual(self.value("worktree_pool_max"), before)
        self.assertIn("Not changed:", self.page(h["Location"].split("#")[0])[2].decode())


if __name__ == "__main__":
    unittest.main()
