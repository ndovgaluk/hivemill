import json
import unittest

from harness import FactoryTestCase, PR_URL, git

SHA = "a" * 40
NOREPLY = {"GIT_COMMITTER_EMAIL": "noreply@github.com", "GIT_COMMITTER_NAME": "GitHub",
           "GIT_AUTHOR_EMAIL": "zz-test@example.invalid", "GIT_AUTHOR_NAME": "zz-test"}


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


class MergedExternallyOpenSquashTests(FactoryTestCase):
    """OPEN PR + matching GitHub squash on origin/main (T-1399)."""

    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_goal()
        e.seed_task("T-0001", status="in_progress")
        e.seed_agent("zz-test-director", "director")
        e.seed_agent("zz-test-coder", "coder", goal="G-001", task="T-0001")
        e.use_git_head()
        self.wt = e.home / "head-wt"
        self.remote = e.home / "head-origin.git"
        if git("remote", cwd=e.home_dir, check=False) != "":
            git("remote", "set-url", "origin", str(self.remote), cwd=e.home_dir)
        else:
            git("remote", "add", "origin", str(self.remote), cwd=e.home_dir)
        e.seed_pr(state="OPEN")
        st = json.loads(e.gh_state.read_text())
        st["prs"][PR_URL]["mergeCommit"] = None
        e.gh_state.write_text(json.dumps(st))

    def squash_on_main(self, msg="feature (#1)", *, merge_tree=True, parent_tip=None):
        git("fetch", "-q", "origin", "main", cwd=self.wt)
        head = git("rev-parse", "HEAD", cwd=self.wt)
        parent = parent_tip or git("rev-parse", "origin/main", cwd=self.wt)
        if merge_tree:
            tree = git("merge-tree", "--write-tree", parent, head, cwd=self.wt)
            sha = git("commit-tree", tree, "-p", parent, "-m", msg, cwd=self.wt, env=NOREPLY)
        else:
            sha = git("commit-tree", f"{head}^{{tree}}", "-p", parent, "-m", msg, cwd=self.wt, env=NOREPLY)
        git("push", "-q", "origin", f"{sha}:refs/heads/main", cwd=self.wt)
        return sha

    def test_open_pr_matching_merge_tree_squash_closes(self):
        main = self.squash_on_main()
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally",
                         "--reason", "GitHub 502", agent="zz-test-director")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.env.sql("SELECT status FROM tasks WHERE id='T-0001'")[0]["status"], "done")
        hist = self.ok("task", "show", "T-0001").stdout
        self.assertIn(main, hist)
        self.assertIn("merged-externally", hist)

    def test_open_pr_wrong_tree_refused(self):
        git("fetch", "-q", "origin", "main", cwd=self.wt)
        git("checkout", "-q", "--detach", "origin/main", cwd=self.wt)
        (self.wt / "wrong-tree.txt").write_text("x\n")
        git("add", "wrong-tree.txt", cwd=self.wt)
        git("commit", "-q", "-m", "feature (#1)", cwd=self.wt, env=NOREPLY)
        sha = git("rev-parse", "HEAD", cwd=self.wt)
        git("push", "-q", "origin", f"{sha}:refs/heads/main", cwd=self.wt)
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally",
                         "--reason", "x", agent="zz-test-director")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("not MERGED", p.stderr)

    def test_open_pr_subject_without_pr_number_refused(self):
        self.squash_on_main(msg="feature (no number)")
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally",
                         "--reason", "x", agent="zz-test-director")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("not MERGED", p.stderr)

    def test_open_pr_squash_beyond_twenty_first_parent_commits_refused(self):
        self.squash_on_main()
        git("fetch", "-q", "origin", "main", cwd=self.wt)
        git("checkout", "-q", "-B", "main", "origin/main", cwd=self.wt)
        for i in range(21):
            git("commit", "-q", "--allow-empty", "-m", f"pad {i}", cwd=self.wt, env=NOREPLY)
            git("push", "-q", "origin", "HEAD:main", cwd=self.wt)
        p = self.env.run("task", "update", "T-0001", "--status", "done", "--merged-externally",
                         "--reason", "x", agent="zz-test-director")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("not MERGED", p.stderr)


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
