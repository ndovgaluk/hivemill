import datetime as dt
import json
import os
import subprocess
import sys
import unittest

from harness import FactoryTestCase, REPO, rendered_settings

HOOK = REPO / "roles" / "hooks" / "boss-inbox.py"


class BossTickTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_agent("boss", "boss", pane_id="p-boss")
        e.seed_agent("zz-director", "director", pane_id="p-dir")
        e.seed_agent("zz-lead", "lead", pane_id="p-lead")
        e.set_herdr(agents=[{"name": n, "pane_id": p, "agent_status": "idle", "agent_session": {"value": "s-" + n}}
                            for n, p in (("boss", "p-boss"), ("zz-director", "p-dir"), ("zz-lead", "p-lead"))])

    def mail(self, to, n=1, kind="request"):
        for i in range(n):
            self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x',?,?,?,?,'t')",
                         (to, kind, f"subj{i}", ""))

    def herdr_calls(self, *cmd):
        return [c["argv"] for c in self.env.calls("herdr") if tuple(c["argv"][:len(cmd)]) == cmd]

    def prompts_to(self, name):
        return [a for a in self.herdr_calls("agent", "prompt") if a[2] == name]

    def badge(self, pane):
        a = [a for a in self.herdr_calls("pane", "report-metadata") if a[2] == pane][-1]
        return a[a.index("--display-agent") + 1]

    def test_boss_with_mail_not_prompted_but_badged(self):
        self.mail("boss", 3)
        self.ok("tick")
        self.assertEqual(self.prompts_to("boss"), [])
        self.assertIn("📬3", self.badge("p-boss"))

    def test_boss_no_mail_plain_badge(self):
        self.ok("tick")
        self.assertEqual(self.prompts_to("boss"), [])
        self.assertNotIn("📬", self.badge("p-boss"))

    def test_director_cycle_never_targets_boss(self):
        self.mail("boss", 1)
        self.ok("tick")
        self.assertEqual(self.prompts_to("boss"), [])
        cycle = [a for a in self.herdr_calls("agent", "prompt") if "Director cycle" in a[3]]
        self.assertEqual([a[2] for a in cycle], ["zz-director"])

    def test_director_and_lead_still_nudged(self):
        self.mail("zz-director", 2)
        self.mail("zz-lead", 1)
        self.ok("tick")
        self.assertIn("📬 2 unread", self.prompts_to("zz-director")[0][3])
        self.assertIn("📬 1 unread", self.prompts_to("zz-lead")[0][3])
        self.assertNotIn("📬", self.badge("p-dir"))


STALE_NOW = dt.datetime(2026, 6, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
STALE_KEY = "stale_unread_alert_s"
STALE_SUBJECT = "stale unread mail:"
STALE_EVENT = "stale-unread-alert"
STALE_AGENTS = (("boss", "boss", "p-boss"), ("zz-director", "director", "p-dir"), ("zz-lead", "lead", "p-lead"),
                ("zz-coder", "coder", "p-coder"))
CODER = "zz-coder"
DIRECTOR = "zz-director"


class StaleUnreadTests(FactoryTestCase):
    """G-003 SC4: one alert per live agent whose unread mail is at least stale_unread_alert_s old. Every agent is
    listed as working, so tick step 3 nudges nobody and only the stale-unread step acts."""

    def setUp(self):
        super().setUp()
        for name, role, pane in STALE_AGENTS:
            self.env.seed_agent(name, role, pane_id=pane)
        self.env.set_herdr(agents=[{"name": n, "pane_id": p, "agent_status": "working", "agent_session": {"value": "s-" + n}}
                                   for n, _, p in STALE_AGENTS])

    def mail(self, to, age_min, kind="request", at=0):
        """One unread message for `to`, `age_min` old at STALE_NOW + `at` minutes."""
        created = (STALE_NOW + dt.timedelta(minutes=at - age_min)).isoformat()
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x',?,?,?,?,?)",
                     (to, kind, "subj", "", created))
        return self.env.sql("SELECT max(id) i FROM messages")[0]["i"]

    def tick(self, plus_min=0):
        self.ok("tick", extra_env={"FACTORY_NOW": (STALE_NOW + dt.timedelta(minutes=plus_min)).isoformat()})

    def alerts(self, about):
        return self.env.sql("SELECT recipient, sender, subject, body FROM messages WHERE kind='alert' AND subject LIKE ? "
                            "ORDER BY id", (f"{STALE_SUBJECT} {about} (%",))

    def alert_events(self, about):
        return [json.loads(r["detail"]) for r in self.env.sql(
            "SELECT detail FROM events WHERE entity='agent' AND entity_id=? AND action=?", (about, STALE_EVENT))]

    def test_default_is_one_hour(self):
        self.assertEqual(self.ok("config", STALE_KEY).stdout.strip().split()[-1], "3600")

    def test_59_min_is_not_stale(self):
        self.mail(CODER, 59)
        self.tick()
        self.assertEqual(self.alerts(CODER), [])
        self.assertEqual(self.alert_events(CODER), [])

    def test_threshold_61_min_alerts_the_director(self):
        mid = self.mail(CODER, 61)
        self.tick()
        (a,) = self.alerts(CODER)
        self.assertEqual((a["recipient"], a["sender"]), (DIRECTOR, "tick"))
        self.assertEqual(a["subject"], f"{STALE_SUBJECT} {CODER} (1 msg, oldest 61 min)")
        self.assertIn(f"M{mid} request from x, 61 min", a["body"])
        self.assertEqual(self.alert_events(CODER), [{"agent": CODER, "count": 1, "oldest": f"M{mid}", "to": "director"}])

    def test_threshold_exactly_60_min_alerts(self):
        self.mail(CODER, 60)
        self.tick()
        self.assertEqual(len(self.alerts(CODER)), 1)

    def test_dedup_one_alert_per_episode_and_a_new_one_after_the_mail_was_read(self):
        self.mail(CODER, 61)
        self.tick()
        self.tick(1)
        self.mail(CODER, 70, at=2)   # a second stale message in the same episode
        self.tick(2)
        self.assertEqual(len(self.alerts(CODER)), 1)
        self.assertEqual(len(self.alert_events(CODER)), 1)
        self.env.sql("UPDATE messages SET read_at='2026-06-01T12:03:00+00:00' WHERE recipient=?", (CODER,))
        self.tick(3)                 # nothing stale: the episode ends
        self.assertEqual(self.env.sql("SELECT 1 FROM throttle WHERE key=?", (f"stale-unread:{CODER}",)), [])
        self.mail(CODER, 61, at=4)
        self.tick(4)
        self.assertEqual(len(self.alerts(CODER)), 2)

    def test_routing_director_to_boss_everyone_else_to_director_once_each(self):
        self.mail(DIRECTOR, 61)
        self.mail("boss", 61, kind="decision")
        self.mail("zz-lead", 61)
        for plus in (0, 1, 2):
            self.tick(plus)
        self.assertEqual([a["recipient"] for a in self.alerts(DIRECTOR)], ["boss"])
        self.assertEqual([a["recipient"] for a in self.alerts("boss")], [DIRECTOR])
        self.assertEqual([a["recipient"] for a in self.alerts("zz-lead")], [DIRECTOR])

    def test_config_threshold_is_honoured(self):
        self.ok("config", STALE_KEY, "600")
        self.mail(CODER, 9)
        self.tick()
        self.assertEqual(self.alerts(CODER), [])
        self.mail("zz-lead", 11)
        self.tick()
        self.assertEqual(len(self.alerts("zz-lead")), 1)

    def test_not_live_agent_is_ignored(self):
        self.env.seed_agent("zz-gone", "coder", status="exited", pane_id="p-gone")
        self.mail("zz-gone", 120)
        self.tick()
        self.assertEqual(self.alerts("zz-gone"), [])


class BossHookTests(FactoryTestCase):
    def hook(self, stdin="{}", env=None, path=None):
        e = self.env.env("boss")
        e.update(env or {})
        if path is not None:
            e["PATH"] = path
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=e, timeout=30)

    def seed(self, subject, body="", kind="report"):
        self.env.sql("INSERT INTO messages(sender,recipient,kind,subject,body,created) VALUES('x','boss',?,?,?,'t')",
                     (kind, subject, body))

    def factory_on_path(self):
        d = self.env.home / "fbin"
        d.mkdir(exist_ok=True)
        (d / "factory").write_text(f"#!/bin/sh\nexec {sys.executable} {REPO / 'bin' / 'factory'} \"$@\"\n")
        (d / "factory").chmod(0o755)
        return f"{d}{os.pathsep}{self.env.env()['PATH']}"

    def test_unread_injected_and_marked_read(self):
        self.seed("hello-owner-subject", "details here")
        p = self.hook(path=self.factory_on_path())
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("Factory inbox", out["additionalContext"])
        self.assertIn("hello-owner-subject", out["additionalContext"])
        self.assertEqual(self.env.sql("SELECT count(*) FROM messages WHERE read_at IS NULL")[0][0], 0)

    def test_empty_inbox_prints_nothing(self):
        p = self.hook(path=self.factory_on_path())
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_factory_failure_prints_nothing(self):
        p = self.hook(env={"FACTORY_HOME": str(self.env.home / "nope" / "x")}, path=self.factory_on_path())
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        p = self.hook(path="/nonexistent")  # no factory on PATH
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_bad_or_empty_stdin(self):
        self.seed("s1")
        for stdin in ("", "{not json", "\x00\x01"):
            p = self.hook(stdin=stdin, path=self.factory_on_path())
            self.assertEqual(p.returncode, 0, repr(stdin))

    def test_truncation(self):
        self.seed("big", "y" * 20000, kind="request")  # reports this long are collapsed
        p = self.hook(path=self.factory_on_path())
        self.assertEqual(p.returncode, 0)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.endswith("(truncated; run factory inbox --all)"))
        self.assertLess(len(ctx), 8100)


class BossSettingsTests(unittest.TestCase):
    def test_boss_json_hook_and_existing_entries(self):
        # asserts only what T-0093 owns; other PRs may edit the rest of boss.json
        cur = json.loads(rendered_settings("boss").read_text())
        self.assertEqual(cur["env"]["FACTORY_ROLE"], "boss")
        for key in ("allow", "deny"):
            self.assertTrue(cur["permissions"][key], key)
        cmds = [h["command"] for g in cur["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
        self.assertEqual(len([c for c in cmds if c.endswith("roles/hooks/boss-inbox.py")]), 1)
        self.assertTrue(HOOK.exists())


if __name__ == "__main__":
    unittest.main()
