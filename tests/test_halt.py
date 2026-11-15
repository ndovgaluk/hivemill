"""HM-44 Urgent stop: `factory halt` stops every agent and holds the factory (no spawn, no merge, a tick that only stops
and reaps); `factory start` clears it. Every check goes through the real CLI as a subprocess (tests/harness.py)."""
import json
import unittest

from harness import FactoryTestCase

FAST = {"FACTORY_STOP_CONFIRM_S": "0.2"}
HALT_MSG = "the factory is halted by the owner (factory halt); start it again with factory start"
LIVE = (("zz-coder", "coder", "p1"), ("zz-lead", "lead", "p2"), ("zz-boss", "boss", "p3"))


class HaltBase(FactoryTestCase):
    INPROC = True

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_goal()
        e.seed_team("g-001-a", lead="zz-lead")
        e.seed_task(status="in_progress", team="g-001-a")
        for name, role, pane in LIVE:
            e.seed_agent(name, role, goal=None if role == "boss" else "G-001",
                         team="g-001-a" if role != "boss" else None, task="T-0001" if role == "coder" else None,
                         pane_id=pane)
            e.sql("UPDATE agents SET session_id=? WHERE name=?", (f"sess-{name}", name))
        e.seed_agent("zz-queued", "coder", goal="G-001", team="g-001-a", status="queued")
        self.herdr(*[(n, p) for n, _, p in LIVE])

    def herdr(self, *specs, **extra):
        self.env.set_herdr(
            workspaces=[{"workspace_id": "w1", "label": "w"}],
            panes=[{"pane_id": p, "tab_id": "t1", "workspace_id": "w1"} for _, p in specs],
            agents=[{"name": n, "agent": "claude", "pane_id": p, "agent_status": "idle"} for n, p in specs], **extra)

    def statuses(self):
        return {r["name"]: r["status"] for r in self.env.sql("SELECT name, status FROM agents")}

    def halt(self, code=0, agent=None, reason="smoke"):
        p = self.env.run("halt", "--reason", reason, agent=agent, extra_env=FAST)
        self.assertEqual(p.returncode, code, f"rc={p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    def halted(self):
        r = self.env.sql("SELECT value FROM config WHERE key='factory_halt'")
        return r[0]["value"] if r else "0"

    def events(self, action):
        return self.env.sql("SELECT * FROM events WHERE entity='factory' AND action=?", (action,))


class HaltTests(HaltBase):
    def test_halt_stops_every_agent_and_sets_the_switch(self):
        p = self.halt()
        st = self.statuses()
        self.assertEqual({n: st[n] for n, _, _ in LIVE}, {"zz-coder": "stopped", "zz-lead": "stopped", "zz-boss": "stopped"})
        self.assertEqual(st["zz-queued"], "cancelled")
        self.assertEqual(self.halted(), "1")
        ev = self.events("halt")
        self.assertEqual([e["detail"] for e in ev], ["smoke"])
        self.assertIn("4 stopped, 0 still closing", p.stdout)

    def test_a_pane_that_does_not_close_is_still_closing_exit_1_and_the_tick_retries(self):
        self.herdr(*[(n, p) for n, _, p in LIVE], pane_close_fail=True)
        p = self.halt(code=1)
        self.assertIn("still closing", p.stdout)
        self.assertEqual(self.statuses()["zz-coder"], "live")
        self.herdr(*[(n, p) for n, _, p in LIVE], pane_close_fail=False)   # the panes close now (set_herdr merges)
        self.env.sql("UPDATE agents SET stop_attempt_at='2026-01-01T00:00:00+00:00' WHERE status='live'")
        self.ok("tick", extra_env=FAST)
        self.assertEqual({self.statuses()[n] for n, _, _ in LIVE}, {"stopped"})

    def test_halt_and_start_are_refused_to_agents(self):
        for cmd in ("halt", "start"):
            with self.subTest(cmd):
                p = self.env.run(cmd, agent="zz-lead")
                self.assertEqual(p.returncode, 3, p.stderr)
        self.assertEqual(self.halted(), "0")
        self.assertEqual(self.statuses()["zz-coder"], "live")

    def test_only_the_owner_sets_the_switch_through_config(self):
        p = self.env.run("config", "factory_halt", "1", agent="zz-director-x")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.halted(), "0")


class WhileHalted(HaltBase):
    def setUp(self):
        super().setUp()
        self.halt()

    def test_spawn_is_refused_for_every_role(self):
        for role in ("coder", "lead", "director"):
            with self.subTest(role):
                p = self.env.run("spawn", role, "--goal", "G-001")
                self.assertEqual(p.returncode, 3, p.stderr)
                self.assertIn(HALT_MSG, p.stderr)

    def test_judge_is_refused(self):
        p = self.env.run("judge", "--merge", "T-0001", agent="zz-judge")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn(HALT_MSG, p.stderr)

    def test_the_tick_starts_wakes_and_nudges_nobody(self):
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) "
                     "VALUES('x','zz-boss','escalation','s','', '2026-01-01T00:00:00+00:00')")
        before = len(self.env.calls("herdr"))
        self.ok("tick", extra_env=FAST)
        verbs = {tuple(c["argv"][:2]) for c in self.env.calls("herdr")[before:]}
        for verb in (("agent", "prompt"), ("agent", "send-keys"), ("pane", "split"), ("tab", "new"), ("agent", "start")):
            self.assertNotIn(verb, verbs)
        self.assertEqual(self.env.sql("SELECT count(*) n FROM agents WHERE status IN ('live','starting','queued')")[0]["n"], 0)
        self.assertEqual(self.env.sql("SELECT count(*) n FROM events WHERE action IN ('spawn','boss-wake','workflow-tick')")[0]["n"], 0)

    def test_start_clears_the_halt_and_spawn_is_accepted_again(self):
        p = self.env.run("start", "--no-up", "--reason", "back")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.halted(), "0")
        self.assertEqual([e["detail"] for e in self.events("start")], ["back"])
        p = self.env.run("spawn", "coder", "--goal", "G-001", "--name", "zz-new")
        self.assertNotIn(HALT_MSG, p.stderr)
        self.assertEqual(self.env.sql("SELECT goal_id FROM tasks WHERE id='T-0001'")[0]["goal_id"], "G-001")
        self.assertEqual(self.env.sql("SELECT status FROM goals WHERE id='G-001'")[0]["status"], "active")


class NotHalted(HaltBase):
    def test_spawn_is_accepted_when_not_halted(self):
        p = self.env.run("spawn", "coder", "--goal", "G-001", "--name", "zz-new")
        self.assertNotIn(HALT_MSG, p.stderr)
        self.assertTrue(self.env.sql("SELECT 1 FROM agents WHERE name='zz-new'"))


if __name__ == "__main__":
    unittest.main()
