"""HM-44: the dashboard's Urgent stop: the header link on every page (loopback only), the /halt confirm page, the halted
banner, and POST /halt and /start behind the Settings guard (loopback, same Origin, form token)."""
import contextlib
import io
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from harness import FactoryTestCase  # noqa: E402
from test_web_server import ServerCase, get  # noqa: E402
from test_web_settings import TOKEN_RE, post  # noqa: E402
from web import server  # noqa: E402
from web.views import halt as halt_view  # noqa: E402

BUTTON = b'class="halt-btn"'


class HaltPages(ServerCase):
    def halt_on(self, reason="smoke test", closing=0):
        self.con.execute("INSERT INTO config(key,value) VALUES('factory_halt','1') ON CONFLICT(key) DO UPDATE SET value='1'")
        self.con.execute("INSERT INTO events(ts,actor,entity,entity_id,action,detail) "
                         "VALUES('2026-11-15T10:00:00+11:00','owner','factory','factory','halt',?)", (reason,))
        for i in range(closing):
            self.con.execute("INSERT INTO agents(name,role,status,started) VALUES(?,'coder','live','x')", (f"zz-c{i}",))
        self.con.commit()

    def running(self):
        return self.con.execute("SELECT COUNT(*) FROM agents WHERE status IN ('queued','starting','live')").fetchone()[0]

    def post(self, *a, **k):
        with contextlib.redirect_stderr(io.StringIO()):
            return post(self.httpd, *a, **k)

    def token(self):
        return TOKEN_RE.search(self.get("/halt")[2]).group(1).decode()

    def test_button_on_every_page_on_loopback_and_absent_on_a_lan_bind(self):
        for path in ("/", "/goals", "/agents", "/settings"):
            with self.subTest(path):
                self.assertIn(BUTTON, self.get(path)[2])
        self.httpd.app.loopback = False
        for path in ("/", "/goals"):
            with self.subTest(lan=path):
                self.assertNotIn(BUTTON, self.get(path)[2])

    def test_button_links_to_a_confirm_page_with_the_form_and_the_count(self):
        self.con.execute("INSERT INTO agents(name,role,status,started) VALUES('zz-a','coder','live','x')")
        self.con.commit()
        n = self.running()
        st, h, body = self.get("/halt")
        self.assertEqual(st, 200)
        text = body.decode()
        self.assertIn('<form method="post" action="/halt"', text)
        self.assertIn(f"{n} agent(s) are queued, starting or running now", text)
        self.assertIn("form-action 'self'", h["Content-Security-Policy"])
        self.assertIn("form-action 'none'", self.get("/goals")[1]["Content-Security-Policy"])   # other pages: no forms

    def test_halted_banner_on_every_page_with_reason_and_closing_count(self):
        self.halt_on("smoke test", closing=2)
        n = self.running()
        for path in ("/", "/goals", "/settings"):
            with self.subTest(path):
                text = self.get(path)[2].decode()
                self.assertIn("Factory halted since 2026-11-15T10:00:00+11:00: smoke test", text)
                self.assertIn(f"{n} agent(s) still closing", text)
                self.assertIn('href="/halt">Start again', text)
                self.assertNotIn(BUTTON.decode(), text)
        self.assertIn('<form method="post" action="/start"', self.get("/halt")[2].decode())

    def test_no_banner_while_running(self):
        self.assertNotIn(b"halt-banner", self.get("/")[2])

    # ── must reject ──

    def test_post_halt_refused_without_token_from_another_origin_or_on_lan(self):
        calls = []
        orig = halt_view.run
        halt_view.run = lambda *a, **k: calls.append(a) or (True, "")
        self.addCleanup(setattr, halt_view, "run", orig)
        tok = self.token()
        self.assertEqual(self.post("/halt", {})[0], 403)                                   # no token
        self.assertEqual(self.post("/halt", {}, token="wrong")[0], 403)                    # wrong token
        self.assertEqual(self.post("/halt", {}, token=tok, origin="http://evil.example")[0], 403)
        self.httpd.app.loopback = False
        self.assertEqual(self.post("/halt", {}, token=tok)[0], 403)
        self.assertEqual(self.post("/start", {}, token=tok)[0], 403)
        self.assertEqual(calls, [])

    def test_post_halt_with_the_token_runs_factory_halt_with_the_reason(self):
        calls = []
        orig = halt_view.run
        halt_view.run = lambda home, args, env=None: calls.append(args) or (True, "factory halted")
        self.addCleanup(setattr, halt_view, "run", orig)
        st, h, _ = self.post("/halt", {"reason": "runaway agents"}, token=self.token())
        self.assertEqual(st, 303)
        self.assertTrue(h["Location"].startswith("/halt?what=halt&done="))
        self.assertEqual(calls, [["halt", "--reason", "runaway agents"]])


class HaltThroughTheCli(FactoryTestCase):
    """Accept path through the real CLI: POST /halt runs `bin/factory halt`, which sets the switch and records the event."""

    def setUp(self):
        super().setUp()
        e = self.env
        self.httpd = server.make_server(e.db_path, "127.0.0.1", 0, (), tokens=lambda: {"rows": []}, defaults={},
                                        factory_home=e.home_dir)
        self.httpd.app.config_env = e.env()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def test_post_halt_then_start(self):
        with contextlib.redirect_stderr(io.StringIO()):
            tok = TOKEN_RE.search(get(self.httpd, "/halt")[2]).group(1).decode()
            st, _, _ = post(self.httpd, "/halt", {"reason": "web smoke"}, token=tok)
        self.assertEqual(st, 303)
        self.assertEqual(self.env.sql("SELECT value FROM config WHERE key='factory_halt'")[0]["value"], "1")
        self.assertEqual([r["detail"] for r in self.env.sql("SELECT detail FROM events WHERE action='halt'")], ["web smoke"])
        with contextlib.redirect_stderr(io.StringIO()):
            page = get(self.httpd, "/")[2].decode()
        self.assertIn("Factory halted since", page)


if __name__ == "__main__":
    unittest.main()
