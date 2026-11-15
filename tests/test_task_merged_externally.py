import json
import unittest

from harness import FactoryTestCase, PR_URL

SHA = "a" * 40


class MergedExternallyTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_goal()
        e.seed_task("T-0001", status="in_progress")
        e.seed_task("T-0002", status="todo", pr_url=None)
        e.sql("UPDATE tasks SET depends_on=? WHERE id='T-0002'", (json.dumps(["T-0001"]),))
        e.seed_agent("zz-test-director", "director")
        e.seed_agent("zz-test-coder", "coder", goal="G-001", task="T-0001")

    def merged(self, state="MERGED", sha=SHA, status="identical"):
        e = self.env
        e.seed_pr(state=state)
        st = json.loads(e.gh_state.read_text())
        st["prs"][PR_URL]["mergeCommit"] = {"oid": sha} if sha else None
        st["api"] = [{"match": ["compare"], "out": {"status": status}}]
        e.gh_state.write_text(json.dumps(st))

    def close(self, agent="zz-test-director"):
        return self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally",
                            "--reason", "owner merged by hand", agent=agent)

    def status(self):
        return self.env.sql("SELECT status FROM tasks WHERE id='T-0001'")[0]["status"]

    def test_director_closes_merged_pr_and_dependants_become_ready(self):
        self.merged()
        self.assertNotIn("T-0002", self.ok("task", "ready").stdout)
        p = self.close()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.status(), "done")
        self.assertIn("T-0002", self.ok("task", "ready").stdout)
        hist = self.ok("task", "show", "T-0001").stdout
        for want in ("zz-test-director", "merged-externally", PR_URL, SHA, "owner merged by hand"):
            self.assertIn(want, hist)

    def test_owner_may_close(self):
        self.merged()
        self.assertEqual(self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally",
                                      "--reason", "x").returncode, 0)
        self.assertEqual(self.status(), "done")

    def test_not_merged_refused(self):
        for state, sha in (("OPEN", None), ("CLOSED", None)):
            self.merged(state=state, sha=sha)
            p = self.close()
            self.assertEqual(p.returncode, 3, p.stderr)
            self.assertIn("not MERGED", p.stderr)
            self.assertEqual(self.status(), "in_progress")

    def test_merge_commit_not_on_base_refused(self):
        self.merged(status="diverged")
        p = self.close()
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("not on main", p.stderr)
        self.assertEqual(self.status(), "in_progress")

    def test_gh_failure_refused(self):
        self.merged()
        st = json.loads(self.env.gh_state.read_text())
        st["api"] = [{"match": ["compare"], "exit": 1, "err": "boom"}]
        self.env.gh_state.write_text(json.dumps(st))
        self.assertEqual(self.close().returncode, 3)
        self.assertEqual(self.status(), "in_progress")

    def test_wrong_role_refused(self):
        self.merged()
        p = self.close(agent="zz-test-coder")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("only the director or the owner", p.stderr)
        self.assertEqual(self.status(), "in_progress")

    def test_worker_claiming_director_refused(self):
        self.merged()
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally", "--reason", "x",
                         agent="zz-test-director", extra_env={"FACTORY_ROLE": "coder"})
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("only the director or the owner", p.stderr)
        self.assertEqual(self.status(), "in_progress")

    def test_runs_after_merge_like_a_judge_merge(self):
        self.merged()
        e = self.env
        e.sql("INSERT INTO lessons(id,title,roles,rule,created,updated) VALUES('L-001','x','all','r','t','t')")
        e.sql("INSERT INTO lesson_links(lesson_id,task_id,created) VALUES('L-001','T-0001','t')")
        e.seed_agent("zz-test-lead", "lead", goal="G-001")
        st = json.loads(e.gh_state.read_text())
        st["prs"][PR_URL]["files"] = [{"path": "roles/lead.md"}]
        e.gh_state.write_text(json.dumps(st))
        p = self.close()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(e.sql("SELECT merged_at FROM lesson_links")[0]["merged_at"])
        self.assertEqual(e.sql("SELECT status FROM lessons")[0]["status"], "applied")
        self.assertTrue(e.sql("SELECT * FROM events WHERE action='roles-changed'"))

    def test_failing_hook_does_not_undo_close(self):
        self.merged()
        st = json.loads(self.env.gh_state.read_text())
        st["files_fail"] = True
        self.env.gh_state.write_text(json.dumps(st))
        p = self.close()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.status(), "done")
        self.assertTrue(self.env.sql("SELECT * FROM events WHERE action='post-merge-hook-failed'"))

    def test_other_flags_refused(self):
        self.merged()
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally", "--reason", "x",
                         "--priority", "1", agent="zz-test-director")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(self.status(), "in_progress")

    def test_already_done_and_no_pr_refused(self):
        self.merged()
        self.env.sql("UPDATE tasks SET status='done' WHERE id='T-0001'")
        self.assertEqual(self.close().returncode, 2)
        p = self.env.run("task", "update", "T-0002", "--status", "done", "--merged-externally", "--reason", "x",
                         agent="zz-test-director")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("not a coder task with a PR", p.stderr)

    def test_manual_close_also_records_a_merged_event_the_engine_reads(self):  # HM-65
        self.merged()
        self.assertEqual(self.close().returncode, 0)
        ev = self.env.sql("SELECT actor, detail FROM events WHERE entity='task' AND entity_id='T-0001' AND action='merged'")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["detail"], f"@{SHA[:8]} by=zz-test-director: merged-externally — owner merged by hand")

    def test_needs_reason(self):
        self.merged()
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally", agent="zz-test-director")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(self.status(), "in_progress")


class HandMergeAcceptTests(MergedExternallyTests.__base__):
    """HM-65: the hourly drift check closes an in_review task whose PR GitHub reports MERGED, only with
    hand_merge_accept on and only when verify_merged_externally passes; the tick runs as a subprocess."""

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_goal()
        e.seed_task("T-0001", status="in_review")
        e.seed_agent("zz-test-director", "director")

    merged = MergedExternallyTests.merged

    def tick(self):
        self.env.sql("DELETE FROM throttle WHERE key='drift'")   # the drift check runs at most hourly
        self.ok("tick")

    def task(self):
        return self.env.sql("SELECT status FROM tasks WHERE id='T-0001'")[0]["status"]

    def events(self, action):
        return [r["detail"] for r in self.env.sql(
            "SELECT detail FROM events WHERE entity='task' AND entity_id='T-0001' AND action=? ORDER BY id", (action,))]

    def d2(self):
        return [r["body"] for r in self.env.sql("SELECT body FROM messages WHERE subject LIKE 'drift G-001%'")
                if "D2 T-0001" in r["body"]]

    def test_off_by_default_leaves_the_task_in_review_with_its_drift_line(self):
        self.merged()
        self.tick()
        self.assertEqual(self.task(), "in_review")
        self.assertEqual(self.events("merged"), [])
        self.assertTrue(self.d2(), "the D2 drift line stays when the switch is off")

    def test_on_and_verified_closes_the_task_as_a_hand_merge(self):
        self.ok("config", "hand_merge_accept", "on")
        self.merged()
        self.tick()
        self.assertEqual(self.task(), "done")
        self.assertEqual(self.events("merged"),
                         [f"@{SHA[:8]} by=github-hand-merge: merged-externally — merged on GitHub outside the factory gate"])
        self.assertTrue(any("merged-externally by=github-hand-merge" in d for d in self.events("update")))
        self.assertEqual(self.d2(), [])

    def test_on_but_merge_commit_not_on_base_closes_nothing_and_records_why_once(self):
        self.ok("config", "hand_merge_accept", "on")
        self.merged(status="diverged")
        self.tick()
        self.tick()
        self.assertEqual(self.task(), "in_review")
        self.assertEqual(self.events("merged"), [])
        unverified = self.events("hand-merge-unverified")
        self.assertEqual(len(unverified), 1)
        self.assertIn("not on main", unverified[0])

    def test_switch_takes_only_off_or_on(self):
        p = self.env.run("config", "hand_merge_accept", "yes")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("hand_merge_accept must be off or on", p.stderr)
        self.assertEqual(self.env.run("config", "hand_merge_accept", "on").returncode, 0)


if __name__ == "__main__":
    unittest.main()
