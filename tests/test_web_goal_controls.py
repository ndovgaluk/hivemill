"""HM-42: the goal page's controls (Pause / Resume, Stop with a confirmation page) and POST /goal-control behind the
Settings guard; the CLI (`factory goal pause|resume|stop`) does the work."""
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
from web.views import goal_control  # noqa: E402

PAUSE_LINK = 'href="/goal-control?goal=G-90&amp;action=pause" title="Pause…" aria-label="Pause goal G-90" class="goal-ctl-icon"'
RESUME_LINK = 'href="/goal-control?goal=G-90&amp;action=resume" title="Resume…" aria-label="Resume goal G-90" class="goal-ctl-icon"'
STOP_LINK = 'href="/goal-control?goal=G-90&amp;action=stop" title="Stop…" aria-label="Stop goal G-90" class="goal-ctl-icon goal-ctl-icon--stop"'
FORM_OF = '<input type="hidden" name="action" value="{}">'


class GoalControlPages(ServerCase):
    def setUp(self):
        super().setUp()
        self.con.execute("INSERT INTO goals(id,project_id,title,status,priority,created,updated) "
                         "VALUES('G-90',NULL,'Ninety','active',2,'2026-11-15T10:00:00+11:00','2026-11-15T10:00:00+11:00')")
        self.con.commit()

    def page(self, path="/goal/G-90"):
        return self.get(path)[2].decode()

    def post(self, *a, **k):
        with contextlib.redirect_stderr(io.StringIO()):
            return post(self.httpd, *a, **k)

    def token(self):
        return TOKEN_RE.search(self.get("/goal-control?goal=G-90&action=pause")[2]).group(1).decode()

    def stub_run(self, answer=(True, "done")):
        calls = []
        orig = goal_control.run
        goal_control.run = lambda home, goal, action, reason, env=None: calls.append((goal, action, reason)) or answer
        self.addCleanup(setattr, goal_control, "run", orig)
        return calls

    def test_an_active_goal_links_pause_and_stop_and_holds_no_form(self):
        text = self.page()
        self.assertIn(PAUSE_LINK, text)
        self.assertIn(STOP_LINK, text)
        self.assertNotIn(RESUME_LINK, text)
        self.assertNotIn('name="token"', text)   # no form token on the goal page (screenshots, scrub scan)
        self.assertIn("form-action 'none'", self.get("/goal/G-90")[1]["Content-Security-Policy"])

    def test_each_action_is_confirmed_on_the_control_page(self):
        for action in ("pause", "resume", "stop"):
            with self.subTest(action):
                st, h, body = self.get(f"/goal-control?goal=G-90&action={action}")
                self.assertEqual(st, 200)
                self.assertIn(FORM_OF.format(action), body.decode())
                self.assertIn("form-action 'self'", h["Content-Security-Policy"])

    def test_a_paused_goal_says_so_and_offers_resume(self):
        self.con.execute("ALTER TABLE goals ADD COLUMN hold TEXT")   # the server test DB predates the column (HM-42)
        self.con.execute("UPDATE goals SET hold='paused' WHERE id='G-90'")
        self.con.execute("INSERT INTO events(ts,actor,entity,entity_id,action,detail) "
                         "VALUES('2026-11-15T11:00:00+11:00','owner','goal','G-90','goal-pause','check the plan')")
        self.con.commit()
        text = self.page()
        self.assertIn("Paused by the owner</strong> since 2026-11-15T11:00:00+11:00: check the plan", text)
        self.assertIn(RESUME_LINK, text)
        self.assertNotIn(PAUSE_LINK, text)

    def test_a_closed_goal_has_no_controls_and_a_lan_bind_shows_commands(self):
        self.con.execute("UPDATE goals SET status='done' WHERE id='G-90'")
        self.con.commit()
        self.assertNotIn(PAUSE_LINK, self.page())
        self.con.execute("UPDATE goals SET status='active' WHERE id='G-90'")
        self.con.commit()
        self.httpd.app.loopback = False
        text = self.page()
        self.assertNotIn("<form", text.split('id="content"', 1)[1].split("flow-root", 1)[0])
        self.assertIn("factory goal pause G-90", text)

    def test_stop_confirmation_lists_the_agents_and_open_prs(self):
        self.con.execute("INSERT INTO agents(name,role,status,goal_id,started) VALUES('zz-c90','coder','live','G-90','x')")
        self.con.execute("INSERT INTO tasks(id,goal_id,title,status,pr_url,created,updated) "
                         "VALUES('T-90','G-90','t','in_review','https://github.com/example/repo/pull/90','x','x')")
        self.con.commit()
        text = self.page("/goal-control?goal=G-90&action=stop")
        self.assertIn("1 agent(s) of the goal are stopped now: zz-c90", text)
        self.assertIn("1 open pull request(s) are left as they are: T-90", text)
        self.assertIn('<input type="hidden" name="action" value="stop">', text)

    # ── must reject ──

    def test_post_refused_without_token_from_another_origin_on_lan_or_with_a_bad_action(self):
        calls = self.stub_run()
        tok = self.token()
        fields = {"goal": "G-90", "action": "pause"}
        self.assertEqual(self.post("/goal-control", fields)[0], 403)
        self.assertEqual(self.post("/goal-control", fields, token=tok, origin="http://evil.example")[0], 403)
        self.assertEqual(self.post("/goal-control", {"goal": "G-90", "action": "restart"}, token=tok)[0], 400)
        self.assertEqual(self.post("/goal-control", {"goal": "G-90; rm", "action": "pause"}, token=tok)[0], 400)
        self.httpd.app.loopback = False
        self.assertEqual(self.post("/goal-control", fields, token=tok)[0], 403)
        self.assertEqual(calls, [])

    def test_post_with_the_token_runs_the_command_and_comes_back_to_the_goal(self):
        calls = self.stub_run((True, "goal G-90 paused"))
        st, h, _ = self.post("/goal-control", {"goal": "G-90", "action": "pause", "reason": "hold on"}, token=self.token())
        self.assertEqual(st, 303)
        self.assertTrue(h["Location"].startswith("/goal/G-90?ctl=pause&done="))
        self.assertEqual(calls, [("G-90", "pause", "hold on")])


class GoalControlThroughTheCli(FactoryTestCase):
    """Accept path through the real CLI: POST /goal-control pause runs `bin/factory goal pause`, which sets the hold."""

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_goal()
        self.httpd = server.make_server(e.db_path, "127.0.0.1", 0, (), tokens=lambda: {"rows": []}, defaults={},
                                        factory_home=e.home_dir)
        self.httpd.app.config_env = e.env()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def test_pause_then_resume(self):
        with contextlib.redirect_stderr(io.StringIO()):
            tok = TOKEN_RE.search(get(self.httpd, "/goal-control?goal=G-001&action=pause")[2]).group(1).decode()
            self.assertEqual(post(self.httpd, "/goal-control", {"goal": "G-001", "action": "pause"}, token=tok)[0], 303)
        self.assertEqual(self.env.sql("SELECT hold FROM goals WHERE id='G-001'")[0]["hold"], "paused")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(post(self.httpd, "/goal-control", {"goal": "G-001", "action": "resume"}, token=tok)[0], 303)
        self.assertIsNone(self.env.sql("SELECT hold FROM goals WHERE id='G-001'")[0]["hold"])


if __name__ == "__main__":
    unittest.main()
