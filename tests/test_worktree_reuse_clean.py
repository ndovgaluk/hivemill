import re
import unittest
from pathlib import Path

from harness import FactoryTestCase, git

URL = "https://github.com/zz-test/repo/pull/%d"
TOTAL_OFF = re.compile(r"^total: \d+ removed, \d+ would remove, \d+ skipped, \d+ orphan\(s\), \d+ sandbox dir\(s\) kept$", re.M)


class WorktreeReuseCleanTests(FactoryTestCase):
    """`factory clean` pools merged worktrees (worktree_reuse=1), trims the pool and judges claims. Real git repos."""

    def setUp(self):
        super().setUp()
        e = self.env
        self.origin = e.home / "origin.git"
        self.repo = e.home / "repo"
        git("init", "-q", "--bare", "-b", "main", str(self.origin), cwd=e.home)
        git("clone", "-q", str(self.origin), str(self.repo), cwd=e.home)
        git("checkout", "-q", "-b", "main", cwd=self.repo)
        (self.repo / "README").write_text("x\n")
        (self.repo / ".gitignore").write_text("node_modules/\n")
        git("add", "README", ".gitignore", cwd=self.repo)
        git("commit", "-q", "-m", "init", cwd=self.repo)
        git("push", "-q", "-u", "origin", "main", cwd=self.repo)
        (e.home_dir / "worktrees").mkdir()
        e.seed_project("zz-test-proj")
        e.sql("UPDATE projects SET repo_path=? WHERE id='zz-test-proj'", (str(self.repo),))
        e.seed_goal(project="zz-test-proj")
        e.seed_agent("zz-test-cleaner", "cleaner", goal="G-001")
        e.seed_agent("zz-test-director", "director")
        e.seed_agent("zz-test-coder", "coder", goal="G-001", status="exited")
        self.cfg_sql("worktree_reuse", "1")
        self.cfg_sql("worktree_pool_max", "2")

    def cfg_sql(self, key, value):
        self.env.sql("INSERT OR REPLACE INTO config(key,value) VALUES (?,?)", (key, value))

    def task(self, n=1, status="done", pr_state="MERGED", with_pr=True):
        """Task T-000<n> with a worktree on factory/t-000<n> holding one pushed commit and an ignored node_modules/x.js."""
        e = self.env
        tid, branch = f"T-000{n}", f"factory/t-000{n}"
        url = URL % n
        wt = e.home_dir / "worktrees" / f"G-001-{tid}"
        git("worktree", "add", "-q", "-b", branch, str(wt), "origin/main", cwd=self.repo)
        (wt / f"f{n}").write_text("work\n")
        git("add", f"f{n}", cwd=wt)
        git("commit", "-q", "-m", f"work {n}", cwd=wt)
        git("push", "-q", "origin", branch, cwd=wt)
        sha = git("rev-parse", "HEAD", cwd=wt)
        (wt / "node_modules").mkdir()
        (wt / "node_modules" / "x.js").write_text("dep\n")
        e.seed_task(tid, status=status, pr_url=url if with_pr else None)
        e.sql("UPDATE tasks SET worktree=?, branch=? WHERE id=?", (str(wt), branch, tid))
        if with_pr:
            e.seed_pr(url, sha=sha, state=pr_state)
        return wt, branch

    def clean(self, *args):
        return self.ok("clean", *args, agent="zz-test-cleaner")

    def pool(self):
        return self.env.sql("SELECT * FROM worktree_pool ORDER BY path")

    def free(self):
        return [r for r in self.pool() if r["state"] == "free"]

    def branches(self):
        return git("branch", "--list", "factory/*", cwd=self.repo)

    def pane_at(self, pane_id, wt):
        self.env.set_herdr(panes=[{"pane_id": pane_id, "tab_id": "t9", "workspace_id": "w9", "cwd": str(wt), "foreground_cwd": str(wt)}])

    def seed_claim(self, path, task_id, reset_ok=1):
        self.env.sql("INSERT OR REPLACE INTO worktree_pool(path, project_id, state, task_id, reset_ok, claimed_at) "
                     "VALUES (?, 'zz-test-proj', 'claimed', ?, ?, '2026-01-01T00:00:00+00:00')", (str(path), task_id, reset_ok))

    def events(self, action):
        return self.env.sql("SELECT detail FROM events WHERE action=?", (action,))

    # 1 release; 10 not an orphan; 9 readers
    def test_release_pools_clean_worktree_and_keeps_ignored_files(self):
        wt, branch = self.task()
        p = self.clean()
        self.assertTrue(wt.exists())
        self.assertEqual((wt / "node_modules" / "x.js").read_text(), "dep\n")
        self.assertFalse((wt / "f1").exists())
        self.assertEqual(git("rev-parse", "HEAD", cwd=wt), git("rev-parse", "origin/main", cwd=self.repo))
        self.assertEqual(git("branch", "--show-current", cwd=wt), "")  # detached
        self.assertEqual(self.branches(), "")
        rows = self.pool()
        self.assertEqual([(r["path"], r["state"], r["task_id"], r["reset_ok"]) for r in rows],
                         [(str(wt.resolve()), "free", None, 0)])
        self.assertIsNone(self.env.sql("SELECT worktree FROM tasks WHERE id='T-0001'")[0]["worktree"])
        self.assertRegex(p.stdout, r"T-0001\s.*\bpooled\b.*kept in pool \(1/2\)")
        self.assertEqual(len(self.events("worktree-pooled")), 1)
        self.assertNotIn("orphan (left alone)", p.stdout)
        self.assertIn("1 pooled", p.stdout)
        # readers of tasks.worktree
        self.ok("task", "show", "T-0001", agent="zz-test-cleaner")
        before = self.pool()
        p2 = self.clean()
        self.assertRegex(p2.stdout, r"T-0001\s.*nothing to remove")
        self.assertTrue(wt.exists())
        self.assertEqual(self.pool(), before)

    # 2 flag off identical
    def test_flag_off_removes_as_today(self):
        self.cfg_sql("worktree_reuse", "0")
        wt, branch = self.task()
        p = self.clean()
        self.assertFalse(wt.exists())
        self.assertEqual(self.branches(), "")
        self.assertEqual(self.pool(), [])
        self.assertRegex(p.stdout, TOTAL_OFF)
        self.assertNotIn("pooled", p.stdout)

    # 3 cap
    def test_cap_and_trim_order(self):
        wts = [self.task(n)[0] for n in range(1, 5)]
        self.clean()
        free = self.free()
        self.assertEqual(len(free), 2)
        kept = {r["path"] for r in free}
        self.assertEqual(sum(1 for w in wts if w.exists()), 2)
        self.assertEqual(kept, {str(w.resolve()) for w in wts if w.exists()})
        self.assertEqual(len(git("worktree", "list", cwd=self.repo).splitlines()), 3)
        before = self.pool()
        self.clean()
        self.assertEqual(self.pool(), before)
        older, newer = sorted(kept)
        self.env.sql("UPDATE worktree_pool SET released_at='2026-01-02T00:00:00+00:00' WHERE path=?", (older,))
        self.env.sql("UPDATE worktree_pool SET released_at='2026-01-01T00:00:00+00:00' WHERE path=?", (newer,))
        self.ok("config", "worktree_pool_max", "1", agent="zz-test-director")
        self.clean()
        self.assertEqual([r["path"] for r in self.free()], [older])  # `newer` has the older released_at: it went
        self.assertFalse(Path(newer).exists())
        self.assertEqual(len(self.events("worktree-pool-trimmed")), 1)
        self.ok("config", "worktree_reuse", "0", agent="zz-test-director")
        self.clean()
        self.assertEqual(self.free(), [])
        self.assertFalse(Path(older).exists())

    # 4 verdicts still gate
    def test_safety_verdicts_still_gate_pooling(self):
        w1, _ = self.task(1)
        (w1 / "f1").write_text("edited\n")
        w2, _ = self.task(2)
        (w2 / "stray.txt").write_text("x\n")
        w3, _ = self.task(3, pr_state="OPEN")
        w4, _ = self.task(4)
        self.env.seed_agent("zz-test-c4", "coder", goal="G-001", task="T-0004", status="queued", pane_id="p4")
        p = self.clean()
        for w in (w1, w2, w3, w4):
            self.assertTrue(w.exists())
        self.assertEqual(self.pool(), [])
        for reason in ("dirty", "untracked files: stray.txt", "PR OPEN", "agent live"):
            self.assertIn(reason, p.stdout)
        self.assertEqual(len(self.branches().splitlines()), 4)

    # 5 claimed never removed
    def test_claimed_row_never_removed(self):
        wt, _ = self.task(5)
        git("checkout", "-q", "--detach", "origin/main", cwd=wt)
        self.env.sql("UPDATE tasks SET status='in_progress', worktree=? WHERE id='T-0005'", (str(wt),))
        self.seed_claim(wt, "T-0005")
        self.cfg_sql("worktree_pool_max", "0")
        spare = self.env.home_dir / "worktrees" / "spare"  # a free row keeps the project in the trim pass
        self.env.sql("INSERT INTO worktree_pool(path, project_id, state, reset_ok, released_at) "
                     "VALUES (?, 'zz-test-proj', 'free', 0, '2026-01-01T00:00:00+00:00')", (str(spare),))
        p = self.clean()
        self.assertTrue(wt.exists())
        r = self.pool()
        self.assertEqual([(x["path"], x["state"], x["task_id"]) for x in r], [(str(wt), "claimed", "T-0005")])
        self.assertIn("pooled kept: claimed by T-0005", p.stdout)

    # 6 claimed and live pane
    def test_claimed_done_task_with_live_pane_kept(self):
        wt, _ = self.task(1)
        self.seed_claim(wt, "T-0001")
        self.pane_at("p1", wt)
        before = self.pool()
        p = self.clean()
        self.assertIn("protected: cwd of a live pane", p.stdout)
        self.assertTrue(wt.exists())
        self.assertEqual(self.pool(), before)
        self.assertEqual(self.env.sql("SELECT worktree FROM tasks WHERE id='T-0001'")[0]["worktree"], str(wt))

    # 7 locked and submodule
    def test_locked_and_submodule_worktrees_not_pooled(self):
        w1, _ = self.task(1)
        git("worktree", "lock", str(w1), cwd=self.repo)
        w2, _ = self.task(2)
        (w2 / ".gitmodules").write_text("[submodule \"s\"]\n\tpath = s\n\turl = ../s\n")
        git("add", ".gitmodules", cwd=w2)
        git("commit", "-q", "-m", "mod", cwd=w2)
        git("push", "-q", "origin", "factory/t-0002", cwd=w2)
        self.env.seed_pr(URL % 2, sha=git("rev-parse", "HEAD", cwd=w2), state="MERGED")
        self.clean()
        self.assertEqual(self.pool(), [])
        self.assertFalse(w2.exists())  # removed as today
        self.assertTrue(w1.exists())   # locked: `worktree remove --force` refuses once, exactly as without the pool

    # 8 stale claims
    def test_stale_claim_path_missing_row_dropped(self):
        gone = self.env.home_dir / "worktrees" / "gone"
        self.seed_claim(gone, "T-0006")
        self.env.seed_task("T-0006", status="in_progress")
        self.clean()
        self.assertEqual(self.pool(), [])
        self.assertEqual(len(self.events("worktree-pool-stale")), 1)

    def stale(self, n=6):
        wt, _ = self.task(n)
        self.env.sql("UPDATE tasks SET worktree=NULL WHERE id=?", (f"T-000{n}",))
        git("checkout", "-q", "--detach", "origin/main", cwd=wt)
        self.seed_claim(wt, f"T-000{n}")
        return wt

    def test_stale_claim_clean_dir_becomes_free(self):
        wt = self.stale()
        p = self.clean()
        r = self.pool()
        self.assertEqual((r[0]["state"], r[0]["task_id"]), ("free", None))
        self.assertTrue(wt.exists())
        self.assertEqual(len(self.events("worktree-pool-stale")), 1)
        self.assertIn("stale claim released", p.stdout)
        self.cfg_sql("worktree_pool_max", "0")
        self.clean()
        self.assertEqual(self.pool(), [])
        self.assertFalse(wt.exists())

    def test_stale_claim_with_untracked_file_kept(self):
        wt = self.stale()
        (wt / "mine.txt").write_text("x\n")
        p = self.clean()
        self.assertRegex(p.stdout, r"stale claim kept: untracked files: mine\.txt")
        self.assertEqual(self.pool()[0]["state"], "claimed")
        self.assertTrue((wt / "mine.txt").exists())

    def test_stale_claim_with_live_pane_kept(self):
        wt = self.stale()
        self.pane_at("p1", wt)
        p = self.clean()
        self.assertIn("stale claim kept: live pane", p.stdout)
        self.assertEqual(self.pool()[0]["state"], "claimed")
        self.assertTrue(wt.exists())

    # 11 dry run
    def test_dry_run_changes_nothing(self):
        wt, _ = self.task()
        head = git("rev-parse", "HEAD", cwd=wt)
        listing = git("worktree", "list", cwd=self.repo)
        p = self.clean("--dry-run")
        self.assertRegex(p.stdout, r"T-0001\s.*would pool")
        self.assertEqual(self.pool(), [])
        self.assertEqual(git("worktree", "list", cwd=self.repo), listing)
        self.assertEqual(git("rev-parse", "HEAD", cwd=wt), head)
        self.assertIn("factory/t-0001", self.branches())


if __name__ == "__main__":
    unittest.main()
