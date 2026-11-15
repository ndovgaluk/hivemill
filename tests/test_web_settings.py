"""HM-1: the Settings page and its one write path, POST /settings (guard tests through the real server).

Must reject: a LAN bind, a missing or foreign Origin, a missing or wrong form token, a non-form body, an oversized body,
an unknown key, an empty value, other methods and other paths. Must accept: a valid POST on a loopback bind, which runs
the real `bin/factory config` against a throwaway FACTORY_HOME, records the value and a `config set` event.
"""
import contextlib
import http.client
import io
import re
import sqlite3
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
MECH_MERGE = "mech_merge"
REVIEW_AUTOSPAWN = "review_autospawn"
HAND_MERGE = "hand_merge_accept"   # HM-65
AUTOMATION_KEYS = ("lead_parking", "lead_less_dispatch", REVIEW_AUTOSPAWN, "coder_ci_handoff", "prcheck_required",
                   "risk_tiers", MECH_MERGE, HAND_MERGE, "workflow_engine", "workflow_reviewer_session", "workflow_ci")
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
        self.assertFalse(server.is_loopback("203.0.113.10"))   # a documentation address: the scrub scan refuses LAN ones
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

    # ── HM-7: the Automation group; the CLI does not validate these keys, so the page offers and accepts fixed values ──

    def test_automation_group_lists_the_six_switches_with_their_options(self):
        text = self.get("/settings")[2].decode()
        self.assertLess(text.index("Worktrees"), text.index("Automation"))
        for key in AUTOMATION_KEYS:
            with self.subTest(key):
                self.assertIn(f'id="set-{key}"', text)
        row = text[text.index(f'id="set-{MECH_MERGE}"'):]
        row = row[:row.index("</form>")]
        self.assertEqual(re.findall(r'<option[^>]*value="([^"]*)"', row), [v for v, _ in settings.OFF_SHADOW_ON])

    def test_hand_merge_row_says_it_bypasses_the_gate_and_offers_off_and_on(self):  # HM-65
        text = self.get("/settings")[2].decode()
        row = text[text.index(f'id="set-{HAND_MERGE}"'):]
        row = row[:row.index("</form>")]
        self.assertIn("Accept pull requests merged by hand on GitHub", text)
        self.assertIn("bypasses the factory&#x27;s merge gate", text.replace("&#39;", "&#x27;"))
        self.assertEqual(re.findall(r'<option[^>]*value="([^"]*)"', row), [v for v, _ in settings.OFF_ON])

    def test_lan_page_shows_commands_for_the_automation_group(self):
        self.httpd.app.loopback = False
        self.httpd.app.defaults = {**(self.httpd.app.defaults or {}), MECH_MERGE: "off"}
        body = self.get("/settings")[2].decode()
        self.assertNotIn("<form", body)
        self.assertIn(f"factory config {MECH_MERGE} shadow", body)   # the first value it is not set to

    def test_api_json_lists_the_options(self):
        import json
        groups = json.loads(self.get("/api/settings.json")[2])["groups"]
        rows = {s["key"]: s for g in groups for s in g["settings"]}
        self.assertEqual(set(AUTOMATION_KEYS) - set(rows), set())
        self.assertEqual([o["value"] for o in rows[MECH_MERGE]["options"]], [v for v, _ in settings.OFF_SHADOW_ON])

    def test_rejects_a_value_the_page_does_not_offer_and_runs_nothing(self):
        calls = []
        orig = settings.apply_change
        settings.apply_change = lambda *a, **k: calls.append(a) or (True, "")
        self.addCleanup(setattr, settings, "apply_change", orig)
        tok = self.token()
        for key, value in ((MECH_MERGE, "maybe"), ("lead_less_dispatch", "on"), ("lead_parking", "2"),
                           (KEY, "2"), ("worktree_pool_max", "abc")):
            with self.subTest(key=key, value=value):
                self.assertEqual(self.post("/settings", {"key": key, "value": value}, token=tok)[0], 400)
        self.assertEqual(calls, [])

    def test_valid_value_accepts_exactly_what_the_page_offers(self):
        for key, s in settings.SETTINGS.items():
            if s.kind == settings.Kind.CHOICE:
                for value, _ in s.options:
                    with self.subTest(key=key, value=value):
                        self.assertTrue(settings.valid_value(key, value))
        self.assertTrue(settings.valid_value("worktree_pool_max", "999"))   # the range stays with the CLI
        self.assertFalse(settings.valid_value("worktree_pool_max", "-1"))

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

    def test_automation_choice_is_written_by_the_cli_and_shown_by_its_label(self):
        st, h, _ = self.submit(REVIEW_AUTOSPAWN, "on")
        self.assertEqual(st, 303, h)
        self.assertEqual(parse_qs(urlsplit(h["Location"]).query), {settings.Q_SAVED: [REVIEW_AUTOSPAWN]})
        self.assertEqual(self.value(REVIEW_AUTOSPAWN), "on")
        ev = self.env.sql("SELECT action, detail FROM events WHERE entity='config' AND entity_id=?", (REVIEW_AUTOSPAWN,))
        self.assertEqual([(r["action"], r["detail"]) for r in ev], [("set", "on")])
        body = self.page(h["Location"].split("#")[0])[2].decode()
        row = body[body.index(f'id="set-{REVIEW_AUTOSPAWN}"'):]
        self.assertRegex(row[:row.index("</form>")], r'class="set-value">On<')

    def test_coder_self_review_off_is_saved_and_other_values_are_refused(self):  # HM-32
        text = self.page()[2].decode()
        self.assertLess(text.index("Worktrees"), text.index("Coder checks"))
        self.assertLess(text.index("Coder checks"), text.index("Automation"))
        row = text[text.index('id="set-coder_self_review"'):]
        row = row[:row.index("</form>")]
        self.assertEqual(re.findall(r'<option[^>]*value="([^"]*)"', row), [v for v, _ in settings.OFF_ON])
        st, h, _ = self.submit("coder_self_review", "off")
        self.assertEqual(st, 303, h)
        self.assertEqual(self.value("coder_self_review"), "off")
        st, _, _ = self.submit("coder_self_review", "maybe")
        self.assertEqual(st, 400)
        self.assertEqual(self.value("coder_self_review"), "off")

    def test_value_the_cli_refuses_is_reported_and_not_written(self):
        before = self.value("worktree_pool_max")
        st, h, _ = self.submit("worktree_pool_max", "999")
        self.assertEqual(st, 303)
        q = parse_qs(urlsplit(h["Location"]).query)
        self.assertEqual(q[settings.Q_ERROR], ["worktree_pool_max"])
        self.assertTrue(q[settings.Q_MSG][0])
        self.assertEqual(self.value("worktree_pool_max"), before)
        self.assertIn("Not changed:", self.page(h["Location"].split("#")[0])[2].decode())


class MergeGatePage(ServerCase):
    """HM-53: the Merge gate group (one row per project) and its write path, POST /settings/gate."""

    def setUp(self):
        super().setUp()
        # the web fixture schema predates the local gate: give it the two parts the group reads (as bin/factory_cli.py SCHEMA)
        self.con.execute("ALTER TABLE projects ADD COLUMN gate_cmd TEXT NOT NULL DEFAULT ''")
        self.con.execute("CREATE TABLE gate_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, kind TEXT NOT NULL, "
                         "status TEXT NOT NULL, head_sha TEXT, cmd TEXT, created TEXT NOT NULL, started TEXT, finished TEXT)")

    def test_a_database_without_the_gate_columns_shows_no_rows(self):
        self.con.execute("DROP TABLE gate_runs")
        self.assertEqual(settings.gate_projects(self.con), [])
        self.assertEqual(self.get("/settings")[0], 200)

    def post(self, *a, **k):
        with contextlib.redirect_stderr(io.StringIO()):
            return post(self.httpd, *a, **k)

    def token(self):
        return TOKEN_RE.search(self.get("/settings")[2]).group(1).decode()

    def row(self, pid="p1"):
        text = self.get("/settings")[2].decode()
        start = text.index(f'id="gate-{pid}"')
        return text[start:text.index('class="set-row"', start + 1) if 'class="set-row"' in text[start + 1:] else None]

    def test_group_lists_each_project_with_its_mode_and_no_run_yet(self):
        text = self.get("/settings")[2].decode()
        self.assertIn("Merge gate", text)
        self.assertLess(text.index("Automation"), text.index("Merge gate"))
        row = self.row()
        self.assertIn('class="set-value">GitHub CI<', row)
        self.assertIn("Last local run: no run yet", row)
        self.assertIn(f'action="{settings.GATE_PATH}"', row)
        self.assertEqual(re.findall(r'<option[^>]*value="([^"]*)"', row[:row.index("</form>")]), list(settings.GATE_CHOICES))
        self.assertIn('id="set-gate_ignore_pending_ci"', text)

    def test_local_and_custom_commands_are_told_apart_and_custom_is_read_only(self):
        self.con.execute("UPDATE projects SET gate_cmd=? WHERE id='p1'", (settings.LOCAL_GATE_CMD,))
        self.assertIn('class="set-value">Local test run<', self.row())
        self.con.execute("UPDATE projects SET gate_cmd='make test' WHERE id='p1'")
        row = self.row()
        self.assertIn('class="set-value">Custom command<', row)
        self.assertIn("make test", row)
        self.assertNotIn(f'action="{settings.GATE_PATH}"', row)

    def test_last_run_is_shown(self):
        self.con.execute("INSERT INTO gate_runs(project_id,kind,status,head_sha,cmd,created,started,finished) VALUES("
                         "'p1','pr','pass',?,'x','2026-11-15T10:00:00+00:00','2026-11-15T10:00:00+00:00','2026-11-15T10:30:00+00:00')",
                         ("a" * 40,))
        self.assertIn("Last local run: #1 pass, 1800 s, started ", self.row())
        self.assertIn("head aaaaaaaa", self.row())

    def test_query_count_does_not_grow_with_gate_runs(self):
        def count():
            n = []
            self.con.row_factory = sqlite3.Row   # the server's connections return named rows
            self.con.set_trace_callback(n.append)
            settings.gate_projects(self.con)
            self.con.set_trace_callback(None)
            self.con.row_factory = None
            return len(n)
        base = count()
        for i in range(20):
            self.con.execute("INSERT INTO gate_runs(project_id,kind,status,cmd,created) VALUES('p1','pr','fail','x',?)", (str(i),))
        self.assertEqual(count(), base)

    def test_refusals_run_nothing(self):
        calls = []
        orig = settings.apply_gate_mode
        settings.apply_gate_mode = lambda *a, **k: calls.append(a) or (True, "")
        self.addCleanup(setattr, settings, "apply_gate_mode", orig)
        tok = self.token()
        good = {"project": "p1", "mode": settings.GateMode.LOCAL}
        self.assertEqual(self.post(settings.GATE_PATH, {**good, "project": "nope"}, token=tok)[0], 400)
        self.assertEqual(self.post(settings.GATE_PATH, {**good, "mode": settings.GateMode.CUSTOM}, token=tok)[0], 400)
        self.assertEqual(self.post(settings.GATE_PATH, good)[0], 403)                       # no token
        self.assertEqual(self.post(settings.GATE_PATH, good, token=tok, origin="http://evil.example")[0], 403)
        self.con.execute("UPDATE projects SET gate_cmd='make test' WHERE id='p1'")
        self.assertEqual(self.post(settings.GATE_PATH, good, token=tok)[0], 400)             # custom command
        self.httpd.app.loopback = False
        self.assertEqual(self.post(settings.GATE_PATH, good, token=tok)[0], 403)             # LAN bind
        self.assertEqual(calls, [])


class MergeGateWrite(FactoryTestCase):
    """HM-53 accept path through the real CLI (`bin/factory project update`)."""

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_project()
        self.httpd = server.make_server(e.db_path, "127.0.0.1", 0, (), tokens=lambda: {"rows": []}, defaults={},
                                        factory_home=e.home_dir)
        self.httpd.app.config_env = e.env()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def switch(self, mode):
        with contextlib.redirect_stderr(io.StringIO()):
            tok = TOKEN_RE.search(get(self.httpd, "/settings")[2]).group(1).decode()
            return post(self.httpd, settings.GATE_PATH, {"project": "zz-test-proj", "mode": mode}, token=tok)

    def row(self):
        return dict(self.env.sql("SELECT gate_cmd, gate_count_cmd, gate_timeout_s, required_checks FROM projects "
                                 "WHERE id='zz-test-proj'")[0])

    def test_switch_to_local_and_back_leaves_the_row_as_it_was(self):
        before = self.row()
        st, h, _ = self.switch(settings.GateMode.LOCAL)
        self.assertEqual(st, 303, h)
        self.assertEqual(parse_qs(urlsplit(h["Location"]).query), {settings.Q_GATE_SAVED: ["zz-test-proj"]})
        on = self.row()
        self.assertEqual((on["gate_cmd"], on["gate_count_cmd"], on["gate_timeout_s"]),
                         (settings.LOCAL_GATE_CMD, settings.LOCAL_GATE_COUNT_CMD, settings.LOCAL_GATE_TIMEOUT_S))
        self.assertEqual(on["required_checks"], before["required_checks"])
        self.assertEqual(self.switch(settings.GateMode.GITHUB)[0], 303)
        self.assertEqual(self.row(), before)
        ev = self.env.sql("SELECT detail FROM events WHERE entity='project' AND entity_id='zz-test-proj' AND action='update'")
        self.assertTrue(any("gate_cmd=" in r["detail"] for r in ev))


if __name__ == "__main__":
    unittest.main()
