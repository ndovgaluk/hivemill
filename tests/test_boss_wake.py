"""T-1199 (G-036 SC4): tick step 3 wakes the boss pane on stale unread escalation/request mail."""
import datetime as dt
import json
import os
import sys
import unittest
from unittest import mock

from harness import FACTORY, FactoryTestCase
from test_auto_clear import PERM, WARN
from test_relaunch_idle import RelaunchIdleCase

T0 = dt.datetime(2026, 6, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
BOSS = "boss"
PANE = "p-boss"


class BossWakeBase(FactoryTestCase):
    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_agent(BOSS, "boss", pane_id=PANE)
        e.seed_agent("zz-director", "director", pane_id="p-dir")
        self.herdr_idle()
        self.ok("config", "boss_wake_after_s", "900")
        self.ok("config", "boss_wake_cooldown_s", "1800")
        self.env.sql("UPDATE agents SET last_nudge=NULL WHERE name=?", (BOSS,))

    def herdr_idle(self, status="idle"):
        self.env.set_herdr(agents=[{"name": BOSS, "pane_id": PANE, "agent_status": status,
                                    "agent_session": {"value": "s-boss"}}],
                           read_text={BOSS: ""})

    def tick(self, when=None):
        extra = {"FACTORY_NOW": (when or T0).isoformat()}
        self.ok("tick", extra_env=extra)

    def mail(self, kind="escalation", age_min=16, to=BOSS):
        created = (T0 - dt.timedelta(minutes=age_min)).isoformat()
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x',?,?,?,?,?)",
                     (to, kind, "subj", "", created))
        return self.env.sql("SELECT max(id) i FROM messages")[0]["i"]

    def prompts(self):
        return [c["argv"] for c in self.env.calls("herdr")
                if c["argv"][:2] == ["agent", "prompt"] and len(c["argv"]) > 2 and c["argv"][2] == BOSS]

    def send_keys(self):
        return [c["argv"] for c in self.env.calls("herdr") if c["argv"][:2] == ["agent", "send-keys"]]

    def wake_events(self):
        return self.env.sql("SELECT detail, action FROM events WHERE entity='agent' AND entity_id=? AND action='boss-wake'",
                            (BOSS,))

    def badge(self):
        meta = [c["argv"] for c in self.env.calls("herdr")
                if tuple(c["argv"][:2]) == ("pane", "report-metadata") and len(c["argv"]) > 2 and c["argv"][2] == PANE]
        self.assertTrue(meta, "expected sidebar badge call")
        return meta[-1][meta[-1].index("--display-agent") + 1]

    def last_nudge(self):
        return self.env.sql("SELECT last_nudge FROM agents WHERE name=?", (BOSS,))[0]["last_nudge"]


class BossWakeTests(BossWakeBase):
    def test_old_escalation_wakes_once(self):
        mid = self.mail("escalation", 16)
        self.tick()
        self.assertEqual(len(self.prompts()), 1)
        self.assertIn("oldest 16 min", self.prompts()[0][3])
        self.assertIn("[escalation]", self.prompts()[0][3])
        ev = self.wake_events()
        self.assertEqual(len(ev), 1)
        detail = json.loads(ev[0]["detail"])
        self.assertEqual(detail, {"count": 1, "oldest": f"M{mid}", "kinds": "escalation"})
        self.assertIsNotNone(self.last_nudge())

    def test_young_escalation_no_wake(self):
        self.mail("escalation", 10)
        self.tick()
        self.assertEqual(self.prompts(), [])
        self.assertEqual(self.wake_events(), [])

    def test_non_escalation_kinds_no_wake(self):
        for kind in ("report", "alert", "decision"):
            with self.subTest(kind=kind):
                self.env.sql("DELETE FROM messages")
                self.mail(kind, 120)
                self.tick()
                self.assertEqual(self.prompts(), [], kind)

    def test_unsent_input_blocks_wake(self):
        self.mail("escalation", 16)
        self.env.set_herdr(read_text={BOSS: "❯ owner draft here\n"})
        self.tick()
        self.assertEqual(self.prompts(), [])

    def test_busy_pane_no_wake(self):
        self.mail("escalation", 16)
        self.herdr_idle(status="blocked")
        self.tick()
        self.assertEqual(self.prompts(), [])

    def test_cooldown_blocks_second_wake(self):
        self.mail("escalation", 16)
        self.tick()
        n_after_first = len(self.prompts())
        self.assertEqual(n_after_first, 1)
        self.mail("request", 20)
        self.tick(T0 + dt.timedelta(minutes=5))
        self.assertEqual(len(self.prompts()), n_after_first)

    def test_sidebar_badge_with_mail(self):
        self.mail("escalation", 16)
        self.tick()
        self.assertIn("📬1", self.badge())  # label prefix is " 📬1"

    def test_old_request_wakes(self):
        self.mail("request", 16)
        self.tick()
        self.assertEqual(len(self.prompts()), 1)
        self.assertIn("[request]", self.prompts()[0][3])

    def test_permission_dialog_no_wake(self):
        self.env.sql("UPDATE agents SET spawn_args=? WHERE name=?", ('{"runtime":"cursor"}', BOSS))
        self.mail("request", 16)
        self.env.set_herdr(agents=[{"name": BOSS, "pane_id": PANE, "agent_status": "idle",
                                    "agent_session": {"value": "s-boss"}}],
                           read_text={BOSS: PERM})
        self.tick()
        self.assertEqual(self.prompts(), [])
        self.assertEqual(self.send_keys(), [])
        self.assertEqual(self.wake_events(), [])

    def test_settings_warning_no_wake(self):
        self.env.sql("UPDATE agents SET spawn_args=? WHERE name=?", ('{"runtime":"cursor"}', BOSS))
        self.mail("escalation", 16)
        self.env.set_herdr(agents=[{"name": BOSS, "pane_id": PANE, "agent_status": "idle",
                                    "agent_session": {"value": "s-boss"}}],
                           read_text={BOSS: WARN})
        self.tick()
        self.assertEqual(self.prompts(), [])
        self.assertEqual(self.send_keys(), [])
        self.assertEqual(self.wake_events(), [])


class BossWakeUnreadable(FactoryTestCase):
    INPROC = True

    def setUp(self):
        super().setUp()
        self.env.seed_agent(BOSS, "boss", pane_id=PANE)
        self.env.set_herdr(agents=[{"name": BOSS, "pane_id": PANE, "agent_status": "idle",
                                    "agent_session": {"value": "s-boss"}}])
        self.ok("config", "boss_wake_after_s", "900")
        created = (T0 - dt.timedelta(minutes=16)).isoformat()
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x','boss','escalation','s','',?)",
                     (created,))

    def test_unreadable_pane_no_wake(self):
        with self.env.load_factory() as mod:
            real = mod.herdr

            def herdr(*args, check=True, timeout=mod.HERDR_TIMEOUT_S):
                if len(args) >= 2 and args[:2] == ("agent", "read"):
                    return None
                return real(*args, check=check, timeout=timeout)

            argv = [str(FACTORY), "tick"]
            os.environ["FACTORY_NOW"] = T0.isoformat()
            saved = os.environ.get("FACTORY_AGENT")
            os.environ["FACTORY_AGENT"] = "tick"
            with mock.patch.object(mod, "herdr", side_effect=herdr):
                old = sys.argv
                sys.argv = argv
                try:
                    mod.main()
                finally:
                    sys.argv = old
                    if saved is None:
                        os.environ.pop("FACTORY_AGENT", None)
                    else:
                        os.environ["FACTORY_AGENT"] = saved
        prompts = [c for c in self.env.calls("herdr") if c["argv"][:2] == ["agent", "prompt"]]
        self.assertEqual(prompts, [])


# T-0026 (G-003 SC1/SC2/SC3/SC5): HQ nudge when the host lists the pane without agent_status (M554),
# and a due nudge that cannot be delivered is reported. Workers and leads are unchanged.
SHAPE = {"agent": "claude"}  # the M554 shape: listed by name and pane, no agent_session, no agent_status


def m554(name, pane):
    return {"name": name, "pane_id": pane, **SHAPE}


class HqBase(FactoryTestCase):
    BOSS, BPANE, DIR, DPANE = "boss", "p-boss", "zz-director", "p-dir"

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_agent(self.BOSS, "boss", pane_id=self.BPANE)
        e.seed_agent(self.DIR, "director", pane_id=self.DPANE)
        e.sql("UPDATE agents SET last_nudge=NULL")
        self.ok("config", "boss_wake_after_s", "900")
        self.ok("config", "boss_wake_cooldown_s", "0")
        self.ok("config", "nudge_cooldown_s", "0")
        self.herdr([m554(self.BOSS, self.BPANE), m554(self.DIR, self.DPANE)])

    def herdr(self, agents, text=None, fg=None):
        panes = [{"pane_id": p, "tab_id": "t1", "workspace_id": "w1", "fg": fg or "claude"}
                 for p in (self.BPANE, self.DPANE)]
        self.env.set_herdr(agents=agents, panes=panes,
                           read_text={self.BOSS: text or "", self.DIR: text or ""})

    def starting(self, name):
        """A just-started agent the host does not list yet stays live (still_starting uses the wall clock)."""
        self.env.sql("UPDATE agents SET started=? WHERE name=?", (dt.datetime.now().astimezone().isoformat(), name))

    def tick(self, plus_min=0):
        self.ok("tick", extra_env={"FACTORY_NOW": (T0 + dt.timedelta(minutes=plus_min)).isoformat()})

    def mail(self, to, kind, age_min=16):
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x',?,?,'subj','',?)",
                     (to, kind, (T0 - dt.timedelta(minutes=age_min)).isoformat()))

    def prompts(self, name):
        return [c["argv"] for c in self.env.calls("herdr")
                if c["argv"][:2] == ["agent", "prompt"] and c["argv"][2] == name]

    def events(self, action):
        return [json.loads(r["detail"]) for r in self.env.sql("SELECT detail FROM events WHERE action=?", (action,))]

    def alerts(self):
        return self.env.sql("SELECT recipient, sender, subject, body FROM messages WHERE kind='alert' AND sender='tick' AND subject LIKE 'nudge undeliverable%'")

    def throttle(self, key):
        return self.env.sql("SELECT 1 FROM throttle WHERE key=?", (key,))


class UnknownStatusTests(HqBase):
    def test_m554_boss(self):
        self.mail(self.BOSS, "escalation")
        self.tick()
        p = self.prompts(self.BOSS)
        self.assertEqual(len(p), 1)
        self.assertIn("📬 1 unread factory message(s) [escalation], oldest 16 min.", p[0][3])
        self.assertEqual(len(self.events("boss-wake")), 1)
        self.assertEqual(self.events("nudge-undeliverable"), [])

    def test_m554_director(self):
        self.mail(self.DIR, "request")
        self.tick()
        p = self.prompts(self.DIR)
        self.assertEqual(len(p), 1)
        self.assertIn("📬 1 unread factory message(s)", p[0][3])

    def test_draft_is_not_overwritten(self):
        self.mail(self.BOSS, "escalation")
        self.mail(self.DIR, "request")
        self.herdr([m554(self.BOSS, self.BPANE), m554(self.DIR, self.DPANE)], text="❯ owner draft here\n")
        self.tick()
        self.assertEqual(self.prompts(self.BOSS) + self.prompts(self.DIR), [])
        self.assertEqual(self.events("nudge-undeliverable"), [])

    def test_busy_pane_foreground(self):
        self.mail(self.BOSS, "escalation")
        self.mail(self.DIR, "request")
        self.herdr([m554(self.BOSS, self.BPANE), m554(self.DIR, self.DPANE)], fg="vim")
        self.tick()
        self.assertEqual(self.prompts(self.BOSS) + self.prompts(self.DIR), [])
        self.assertEqual(self.alerts(), [])

    def test_working_status_is_not_undeliverable(self):
        self.mail(self.BOSS, "escalation")
        self.herdr([{**m554(self.BOSS, self.BPANE), "agent_status": "working"}, m554(self.DIR, self.DPANE)])
        self.tick()
        self.assertEqual(self.prompts(self.BOSS), [])
        self.assertEqual(self.events("nudge-undeliverable"), [])
        self.assertEqual(self.alerts(), [])

    def test_worker_unknown_status_gets_nothing(self):
        e = self.env
        e.seed_goal()
        e.seed_team(lead="zz-lead")
        e.seed_agent("zz-pm", "pm", goal="G-001", team="g-001-a", pane_id="p-pm")
        e.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x','zz-pm','msg','s','',?)",
              (T0.isoformat(),))
        e.set_herdr(agents=[m554("zz-pm", "p-pm")])
        self.tick()
        self.assertEqual(self.prompts("zz-pm"), [])
        self.assertEqual(self.events("nudge-undeliverable"), [])
        self.assertEqual(self.alerts(), [])


class UndeliverableTests(HqBase):
    def test_undeliverable_boss_no_host_entry(self):
        self.mail(self.BOSS, "escalation")
        self.starting(self.BOSS)
        self.herdr([m554(self.DIR, self.DPANE)])
        self.tick()
        ev = self.events("nudge-undeliverable")
        self.assertEqual(ev, [{"agent": "boss", "role": "boss", "pane": self.BPANE, "reason": "no-host-entry"}])
        a = self.alerts()
        self.assertEqual([(x["recipient"], x["subject"]) for x in a],
                         [(self.DIR, "nudge undeliverable: boss (no-host-entry)")])

    def test_undeliverable_director_prompt_failed(self):
        self.mail(self.DIR, "request")
        self.env.sql("UPDATE agents SET last_nudge=5 WHERE name=?", (self.DIR,))
        self.env.set_herdr(fail_cmds=["agent prompt"])
        self.tick()
        self.assertEqual(self.events("nudge-undeliverable")[0]["reason"], "prompt-failed")
        a = self.alerts()
        self.assertEqual([(x["recipient"], x["subject"]) for x in a],
                         [(self.BOSS, f"nudge undeliverable: {self.DIR} (prompt-failed)")])
        self.assertEqual(self.env.sql("SELECT last_nudge FROM agents WHERE name=?", (self.DIR,))[0][0], 5)

    def test_dedup_and_reset(self):
        key = "nudge-undeliverable:boss:no-host-entry"
        self.mail(self.BOSS, "escalation", age_min=60)
        self.starting(self.BOSS)
        self.herdr([m554(self.DIR, self.DPANE)])
        for m in (0, 2, 4):
            self.tick(m)
        self.assertEqual((len(self.events("nudge-undeliverable")), len(self.alerts())), (1, 1))
        self.assertTrue(self.throttle(key))
        self.herdr([{**m554(self.BOSS, self.BPANE), "agent_status": "idle"}, m554(self.DIR, self.DPANE)])
        self.tick(6)
        self.assertEqual(len(self.prompts(self.BOSS)), 1)
        self.assertFalse(self.throttle(key))
        self.herdr([m554(self.DIR, self.DPANE)])
        self.tick(8)
        self.assertEqual((len(self.events("nudge-undeliverable")), len(self.alerts())), (2, 2))

    def test_not_due_is_not_reported(self):
        self.herdr([])
        self.mail(self.BOSS, "escalation", age_min=5)  # younger than boss_wake_after_s
        self.tick()
        self.assertEqual(self.events("nudge-undeliverable"), [])


class RelaunchNudgeTests(RelaunchIdleCase):
    def after(self, name, shape):
        """The host entry after the relaunch: the row's (possibly new) pane, foreground only claude."""
        pane = self.env.sql("SELECT pane_id FROM agents WHERE name=?", (name,))[0][0]
        entry = {"name": name, "agent": "claude", "pane_id": pane}
        if shape == "idle":
            entry.update(agent_status="idle", agent_session={"value": "sess-" + name})
        panes = [{"pane_id": pane, "tab_id": "t1", "workspace_id": "w1", "fg": "claude"}]
        self.env.set_herdr(agents=[entry], panes=panes, read_text={name: ""})

    def case(self, name, role, pane, fresh):
        self.ok("config", "boss_wake_cooldown_s", "0")
        self.ok("config", "nudge_cooldown_s", "0")
        self.env.sql("UPDATE agents SET last_nudge=NULL")
        self.env.set_herdr(
            agents=[{"name": name, "agent": "claude", "pane_id": pane, "agent_status": "idle",
                     "agent_session": {"value": "sess-boss" if role == "boss" else "sess-dir"}}],
            panes=[{"pane_id": pane, "tab_id": "t1", "workspace_id": "w1"}])
        self.ok("relaunch", name, *(["--fresh"] if fresh else []), agent="zz-boss" if role == "director" else "zz-director")
        self.assertEqual(len(self.starts()), 1)
        self.after(name, "idle" if fresh else "unknown")
        kind = "escalation" if role == "boss" else "request"
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x',?,?,'s','',?)",
                     (name, kind, "2026-05-31T00:00:00+00:00"))
        self.env.calls_file.write_text("")
        self.ok("tick", extra_env={"FACTORY_NOW": "2026-06-01T12:00:00+00:00"})
        p = [c["argv"] for c in self.env.calls("herdr") if c["argv"][:3] == ["agent", "prompt", name]]
        self.assertEqual(len(p), 1)

    def test_relaunch_boss_resumed(self):
        self.case("zz-boss", "boss", "p-boss", False)

    def test_relaunch_boss_fresh(self):
        self.case("zz-boss", "boss", "p-boss", True)

    def test_relaunch_director_resumed(self):
        self.case("zz-director", "director", "p-director", False)

    def test_relaunch_director_fresh(self):
        self.case("zz-director", "director", "p-director", True)


if __name__ == "__main__":
    unittest.main()
