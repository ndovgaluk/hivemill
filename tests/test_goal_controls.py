"""HM-42: the owner's goal controls: `factory goal pause|resume|stop G`. A held goal (goals.hold) starts nobody: a command
refuses with exit 3, the tick skips the start and records it. Through the real CLI as a subprocess (tests/harness.py)."""
import unittest

from harness import FactoryTestCase

FAST = {"FACTORY_STOP_CONFIRM_S": "0.2"}
LIVE = (("zz-coder", "coder", "p1"), ("zz-lead", "lead", "p2"))


class GoalControlBase(FactoryTestCase):
    INPROC = True

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_goal()                                   # G-001
        e.seed_team("g-001-a", lead="zz-lead")
        e.seed_task(status="in_progress", team="g-001-a")
        for name, role, pane in LIVE:
            e.seed_agent(name, role, goal="G-001", team="g-001-a", task="T-0001" if role == "coder" else None, pane_id=pane)
            e.sql("UPDATE agents SET session_id=? WHERE name=?", (f"sess-{name}", name))
        e.seed_agent("zz-boss", "boss", pane_id="p9")    # HQ: not the goal's
        e.sql("UPDATE agents SET session_id='sess-boss' WHERE name='zz-boss'")
        e.set_herdr(workspaces=[{"workspace_id": "w1", "label": "w"}],
                    panes=[{"pane_id": p, "tab_id": "t1", "workspace_id": "w1"} for p in ("p1", "p2", "p9")],
                    agents=[{"name": n, "agent": "claude", "pane_id": p, "agent_status": "idle"}
                            for n, p in (("zz-coder", "p1"), ("zz-lead", "p2"), ("zz-boss", "p9"))])

    def goal(self, *args, agent=None, code=0):
        p = self.env.run("goal", *args, agent=agent, extra_env=FAST)
        self.assertEqual(p.returncode, code, f"goal {args}: rc={p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    def hold(self):
        return self.env.sql("SELECT hold FROM goals WHERE id='G-001'")[0]["hold"]

    def status(self, name):
        return self.env.sql("SELECT status FROM agents WHERE name=?", (name,))[0]["status"]

    def events(self, action):
        return [r["detail"] for r in self.env.sql("SELECT detail FROM events WHERE entity='goal' AND entity_id='G-001' "
                                                 "AND action=? ORDER BY id", (action,))]


class PauseResume(GoalControlBase):
    def test_pause_holds_the_goal_and_stops_its_agents_only(self):
        p = self.goal("pause", "G-001", "--reason", "check the plan")
        self.assertEqual(self.hold(), "paused")
        self.assertEqual((self.status("zz-coder"), self.status("zz-lead"), self.status("zz-boss")),
                         ("stopped", "stopped", "live"))
        self.assertEqual(self.events("goal-pause"), ["check the plan"])
        self.assertIn("2 agent(s) stopped, 0 still closing", p.stdout)

    def test_a_paused_goal_refuses_a_start_and_another_goal_does_not(self):
        self.goal("pause", "G-001")
        p = self.env.run("spawn", "coder", "--goal", "G-001", "--name", "zz-new")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("goal G-001 is paused by the owner", p.stderr)
        self.env.sql("INSERT INTO goals(id,project_id,title,status,priority,created,updated) "
                     "VALUES('G-002','p1','other','active',2,'x','x')")
        p = self.env.run("spawn", "coder", "--goal", "G-002", "--name", "zz-other")
        self.assertNotIn("paused by the owner", p.stderr)

    def test_resume_clears_the_hold_and_starts_are_accepted_again(self):
        self.goal("pause", "G-001")
        self.goal("resume", "G-001", "--reason", "plan ok")
        self.assertIsNone(self.hold())
        self.assertEqual(self.events("goal-resume"), ["plan ok"])
        p = self.env.run("spawn", "coder", "--goal", "G-001", "--name", "zz-new")
        self.assertNotIn("paused by the owner", p.stderr)

    def test_the_tick_skips_a_held_goal_and_goes_on(self):
        self.goal("pause", "G-001")
        self.ok("config", "lead_parking", "1")
        self.env.sql("UPDATE teams SET parked_at='2026-01-01T00:00:00+00:00' WHERE id='g-001-a'")
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) "
                     "VALUES('zz-boss','zz-lead','request','go on','', '2026-01-01T00:00:00+00:00')")
        p = self.env.run("tick", extra_env=FAST)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotEqual(self.status("zz-lead"), "live")
        self.assertTrue(self.events("spawn-held"), "a skipped start is recorded")

    def test_resume_of_a_goal_that_is_not_paused_is_refused(self):
        p = self.goal("resume", "G-001", code=2)
        self.assertIn("not paused", p.stderr)


class Stop(GoalControlBase):
    def test_stop_holds_cancels_and_lists_the_open_pr(self):
        self.env.sql("UPDATE tasks SET pr_url='https://github.com/example/repo/pull/7' WHERE id='T-0001'")
        p = self.goal("stop", "G-001", "--reason", "wrong direction")
        self.assertEqual(self.hold(), "stopped")
        self.assertEqual(self.env.sql("SELECT status FROM goals WHERE id='G-001'")[0]["status"], "cancelled")
        self.assertIn("open PR left as it is: T-0001 https://github.com/example/repo/pull/7", p.stdout)
        self.assertEqual(self.events("goal-stop"), ["wrong direction"])
        p = self.goal("resume", "G-001", code=2)          # a stopped goal is not resumed
        self.assertIn("is cancelled", p.stderr)


class Roles(GoalControlBase):
    def test_a_lead_or_worker_may_not_and_the_director_may(self):
        for agent in ("zz-lead", "zz-coder"):
            with self.subTest(agent):
                self.assertEqual(self.env.run("goal", "pause", "G-001", agent=agent).returncode, 3)
        self.assertIsNone(self.hold())
        self.env.seed_agent("zz-director", "director")
        self.goal("pause", "G-001", agent="zz-director")
        self.assertEqual(self.hold(), "paused")


if __name__ == "__main__":
    unittest.main()
