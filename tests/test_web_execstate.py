"""HM-47: one execution state per goal and task (web/execstate.py), the same on every page, always text plus colour."""
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_web_server import ServerCase  # noqa: E402
from web import execstate  # noqa: E402

T = "2026-11-15T10:00:00+11:00"


class StateCase(ServerCase):
    def setUp(self):
        super().setUp()
        x = self.con.execute
        if "hold" not in {r[1] for r in x("PRAGMA table_info(goals)")}:
            x("ALTER TABLE goals ADD COLUMN hold TEXT")   # the server test DB predates the column (HM-42)
        x("INSERT INTO goals(id,project_id,title,status,priority,created,updated) VALUES('G-50',NULL,'Fifty','active',2,?,?)", (T, T))
        x("INSERT INTO tasks(id,goal_id,title,status,created,updated) VALUES('T-50','G-50','build it','in_progress',?,?)", (T, T))
        self.con.commit()

    def agent(self, name, role, status="live", task="T-50", stop=None, failed=None):
        self.con.execute("INSERT INTO agents(name,role,status,goal_id,task_id,started,stop_requested_at,stop_failed_kind) "
                         "VALUES(?,?,?,'G-50',?,?,?,?)", (name, role, status, task, T, stop, failed))
        self.con.commit()

    def st(self, kind="goals", oid="G-50"):
        self.con.row_factory = sqlite3.Row
        return execstate.states(self.con)[kind][oid]

    def set(self, sql, *args):
        self.con.execute(sql, args)
        self.con.commit()


class TestDerivation(StateCase):
    def test_running_names_who(self):
        self.agent("coder-t-50", "coder")
        self.assertEqual((self.st()["state"], self.st()["reason"]), ("running", "coder coder-t-50"))
        self.assertEqual(self.st("tasks", "T-50")["state"], "running")

    def test_waiting_after_the_coder_ended_says_why(self):
        self.set("UPDATE tasks SET status='in_review' WHERE id='T-50'")
        t = self.st("tasks", "T-50")
        self.assertEqual((t["state"], t["reason"]), ("waiting", "review and CI on its PR"))
        self.assertEqual(self.st()["state"], "waiting")      # never just "Active"

    def test_paused_goal_and_its_tasks_are_paused_not_blocked(self):
        self.agent("coder-t-50", "coder", status="stopped")
        self.set("UPDATE goals SET hold='paused', status='blocked' WHERE id='G-50'")
        self.assertEqual((self.st()["state"], self.st()["label"]), ("paused", "Paused"))
        self.assertEqual(self.st("tasks", "T-50")["state"], "paused")

    def test_blocked_names_whom_it_waits_on_and_is_red_only_for_the_owner(self):
        self.set("UPDATE tasks SET status='blocked', waits='owner' WHERE id='T-50'")
        self.set("UPDATE goals SET status='blocked' WHERE id='G-50'")
        t, g = self.st("tasks", "T-50"), self.st()
        self.assertEqual((t["label"], t["tone"]), ("Blocked: owner", "bad"))
        self.assertEqual((g["label"], g["tone"]), ("Blocked: owner", "bad"))
        self.set("UPDATE tasks SET waits='internal' WHERE id='T-50'")
        self.assertEqual(self.st("tasks", "T-50")["tone"], "muted")

    def test_a_requested_stop_not_closed_is_stopping_with_the_failure(self):
        self.agent("coder-t-50", "coder", stop=T, failed="close-failed")
        g = self.st()
        self.assertEqual(g["state"], "stopping")
        self.assertIn("coder-t-50", g["reason"])
        self.assertIn("close-failed", g["reason"])

    def test_stopped_by_the_owner_and_the_factory_halt(self):
        self.set("UPDATE goals SET hold='stopped', status='cancelled' WHERE id='G-50'")
        self.assertEqual(self.st()["state"], "stopped")
        self.set("UPDATE goals SET hold=NULL, status='active' WHERE id='G-50'")
        self.set("INSERT INTO config(key,value) VALUES('factory_halt','1')")
        self.assertEqual((self.st()["state"], self.st()["reason"]), ("paused", "the factory is halted (Urgent stop)"))

    def test_query_count_does_not_grow_with_goals_tasks_or_agents(self):
        def count():
            n = []
            self.con.row_factory = sqlite3.Row
            self.con.set_trace_callback(lambda s: n.append(s) if s.lstrip().upper().startswith("SELECT") else None)
            execstate.states(self.con)
            self.con.set_trace_callback(None)
            return len(n)
        before = count()
        for i in range(60, 80):
            self.con.execute("INSERT INTO goals(id,project_id,title,status,priority,created,updated) VALUES(?,NULL,'g','active',2,?,?)",
                             (f"G-{i}", T, T))
            self.con.execute("INSERT INTO tasks(id,goal_id,title,status,created,updated) VALUES(?,?,'t','in_progress',?,?)",
                             (f"T-{i}", f"G-{i}", T, T))
            self.con.execute("INSERT INTO agents(name,role,status,goal_id,task_id,started) VALUES(?,'coder','live',?,?,?)",
                             (f"c-{i}", f"G-{i}", f"T-{i}", T))
        self.con.commit()
        self.assertEqual(count(), before)


class TestSameEverywhere(StateCase):
    def test_goal_page_goals_list_and_overview_show_the_same_state(self):
        self.agent("coder-t-50", "coder")
        badge = r'<span class="badge badge--info" title="coder coder-t-50" data-state="running">Running</span>'
        for path in ("/goal/G-50", "/goals", "/"):
            with self.subTest(path):
                self.assertRegex(self.get(path)[2].decode(), badge)

    def test_task_page_and_table_show_the_task_state_as_text(self):
        self.agent("coder-t-50", "coder")
        for path in ("/task/T-50", "/tasks"):
            with self.subTest(path):
                text = self.get(path)[2].decode()
                self.assertRegex(text, r'data-state="running">Running</span>')

    def test_every_state_badge_has_visible_text(self):
        self.agent("coder-t-50", "coder")
        for path in ("/goal/G-50", "/goals", "/tasks", "/task/T-50"):
            for label in re.findall(r'data-state="[a-z]+">([^<]*)</span>', self.get(path)[2].decode()):
                self.assertTrue(label.strip(), path)

    def test_the_legend_lists_every_state(self):
        text = self.get("/goals")[2].decode()
        self.assertIn("What the states mean", text)
        for label in execstate.LABEL.values():
            self.assertIn(f">{label}</span>", text)


if __name__ == "__main__":
    unittest.main()
