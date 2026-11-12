import ast
import os
import re
import shutil
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

    # 15 gitdir ownership (director M107 option A), flag on and off
    def _admin_state(self, s):
        admin = Path(git("rev-parse", "--git-dir", cwd=s))
        names = ["HEAD", "index", "ORIG_HEAD", "logs/HEAD"]
        return {n: ((admin / n).read_bytes() if (admin / n).exists() else None) for n in names}

    def _forged_gitdir_case(self, reuse):
        self.cfg_sql("worktree_reuse", reuse)
        w, _ = self.task(1)
        s, _ = self.task(2, status="in_progress", with_pr=False)
        before = self._admin_state(s)
        s_head = git("rev-parse", "HEAD", cwd=s)
        (w / ".git").write_text(f"gitdir: {self.repo}/.git/worktrees/{s.name}\n")
        for run in (1, 2):
            p = self.clean()
            self.assertRegex(p.stdout, r"T-0001\s.*kept: gitdir mismatch")
            self.assertTrue(w.exists())
            self.assertEqual(self.pool(), [])
            self.assertEqual(self._admin_state(s), before)
            self.assertEqual(git("rev-parse", "HEAD", cwd=s), s_head)
            self.assertEqual(git("branch", "--show-current", cwd=s), "factory/t-0002")
            self.assertEqual(len(self.events("worktree-gitdir-mismatch")), 1)
            msgs = self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'")
            self.assertEqual(len(msgs), 1, f"run {run}")
            self.assertIn(str(w.resolve()), msgs[0]["subject"])

    def test_forged_gitdir_kept_flag_on(self):
        self._forged_gitdir_case("1")

    def test_forged_gitdir_kept_flag_off(self):
        self._forged_gitdir_case("0")

    # 21 a task dir with no .git at all keeps today's "not a git worktree", no alert, flag on and off
    def _no_git_case(self, reuse):
        self.cfg_sql("worktree_reuse", reuse)
        w, _ = self.task(1)
        (w / ".git").unlink()
        p = self.clean()
        self.assertRegex(p.stdout, r"T-0001\s.*not a git worktree")
        self.assertNotIn("gitdir mismatch", p.stdout)
        self.assertTrue(w.exists())
        self.assertEqual(self.pool(), [])
        self.assertEqual(self.events("worktree-gitdir-mismatch"), [])
        self.assertEqual(self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'"), [])

    def test_no_git_dir_keeps_not_a_git_worktree_flag_on(self):
        self._no_git_case("1")

    def test_no_git_dir_keeps_not_a_git_worktree_flag_off(self):
        self._no_git_case("0")

    def test_forged_gitdir_claimed_stale_row_kept(self):
        s, _ = self.task(2, status="in_progress", with_pr=False)
        before = self._admin_state(s)
        w = self.env.home_dir / "worktrees" / "forged-claim"
        git("worktree", "add", "-q", "--detach", str(w), "origin/main", cwd=self.repo)
        (w / ".git").write_text(f"gitdir: {self.repo}/.git/worktrees/{s.name}\n")
        self.env.seed_task("T-0006", status="done")
        self.seed_claim(w, "T-0006")
        p = self.clean()
        self.assertRegex(p.stdout, r"kept: gitdir mismatch")
        self.assertEqual(self._admin_state(s), before)
        self.assertEqual([r["state"] for r in self.pool()], ["claimed"])

    # 17 hardened submodule check: a replace ref must not hide .gitmodules
    def test_replace_ref_cannot_hide_gitmodules(self):
        w, _ = self.task(1)
        plain_tree_commit = git("rev-parse", "HEAD", cwd=w)
        (w / ".gitmodules").write_text("[submodule \"s\"]\n\tpath = s\n\turl = ../s\n")
        git("add", ".gitmodules", cwd=w)
        git("commit", "-q", "-m", "mod", cwd=w)
        git("push", "-q", "origin", "factory/t-0001", cwd=w)
        self.env.seed_pr(URL % 1, sha=git("rev-parse", "HEAD", cwd=w), state="MERGED")
        # plain git now reads the commit without .gitmodules
        git("replace", "HEAD", plain_tree_commit, cwd=w)
        self.assertNotEqual(git("rev-parse", "HEAD", cwd=w), "")
        self.clean()
        self.assertEqual(self.pool(), [])
        self.assertFalse(w.exists())  # treated as a submodule worktree: removed as today, not pooled

    # ---- 19 ownership helper (staff-engineer design M125/M128): T1-T12. S is a live in-progress sibling that must never change.
    def sib(self):
        s, _ = self.task(2, status="in_progress", with_pr=False)
        return s, self._admin_state(s), git("rev-parse", "HEAD", cwd=s)

    def s_intact(self, s, snap, head):
        self.assertTrue(s.is_dir())
        self.assertEqual(self._admin_state(s), snap)
        self.assertEqual(git("rev-parse", "HEAD", cwd=s), head)

    def admin_of(self, w):
        return Path(git("rev-parse", "--git-dir", cwd=w))

    def wroot(self):
        return self.repo / ".git" / "worktrees"

    def runs(self):
        """clean with the flag on and then off; each time the output must say gitdir mismatch."""
        paths = [r["path"] for r in self.pool()]
        for flag in ("1", "0"):
            self.cfg_sql("worktree_reuse", flag)
            p = self.clean()
            self.assertIn("kept: gitdir mismatch", p.stdout, f"flag {flag}")
            for path in paths:  # every seeded pool row, not just one of them, is refused for the ownership reason
                self.assertTrue(any(path in l and "kept: gitdir mismatch" in l for l in p.stdout.splitlines()),
                                f"flag {flag}: {path} not refused as a gitdir mismatch:\n{p.stdout}")

    def free_row(self, path):
        self.env.sql("INSERT OR REPLACE INTO worktree_pool(path, project_id, state, task_id, reset_ok, released_at) "
                     "VALUES (?, 'zz-test-proj', 'free', NULL, 0, '2026-01-01T00:00:00+00:00')", (str(path),))

    def test_t1_normal_and_relative_pointers_pass(self):
        w, _ = self.task(1)
        a = self.admin_of(w)
        (w / ".git").write_text("gitdir: " + os.path.relpath(a, w) + "\n")
        (a / "gitdir").write_text(os.path.relpath(w / ".git", a) + "\n")
        p = self.clean()
        self.assertRegex(p.stdout, r"T-0001\s.*pooled")
        self.assertEqual([r["path"] for r in self.free()], [str(w)])

    def test_t2_symlinked_pool_dir_never_touches_sibling(self):
        s, snap, head = self.sib()
        link = self.env.home_dir / "worktrees" / "link"
        link.symlink_to(s)
        self.env.seed_task("T-0006", status="done")
        self.seed_claim(link, "T-0006")  # stale-claim route
        self.runs()
        self.s_intact(s, snap, head)
        self.assertEqual([r["state"] for r in self.pool()], ["claimed"])
        self.env.sql("DELETE FROM worktree_pool")  # trim route, cap 0
        self.free_row(link)
        self.cfg_sql("worktree_pool_max", "0")
        self.runs()
        self.s_intact(s, snap, head)
        self.assertEqual([r["state"] for r in self.pool()], ["free"])
        self.env.sql("DELETE FROM worktree_pool")  # task route: a done task recorded the symlink
        self.env.seed_task("T-0007", status="done", pr_url=URL % 7)
        self.env.sql("UPDATE tasks SET worktree=?, branch='factory/t-0007' WHERE id='T-0007'", (str(link),))
        self.runs()
        self.s_intact(s, snap, head)

    def test_t3_symlinked_parent_refused(self):
        s, snap, head = self.sib()
        real = self.env.home_dir / "realparent"
        real.mkdir()
        w = real / "W"
        git("worktree", "add", "-q", "--detach", str(w), "origin/main", cwd=self.repo)
        (self.env.home_dir / "worktrees" / "alias").symlink_to(real)
        self.env.seed_task("T-0006", status="done")
        self.seed_claim(self.env.home_dir / "worktrees" / "alias" / "W", "T-0006")
        self.runs()
        self.assertTrue(w.is_dir())
        self.s_intact(s, snap, head)

    def test_t4_dotgit_symlink_and_dir_refused(self):
        s, snap, head = self.sib()
        w = self.stale(6)
        (w / ".git").unlink()
        (w / ".git").symlink_to(s / ".git")
        self.runs()
        self.s_intact(s, snap, head)
        self.assertTrue(w.is_dir())
        d = self.env.home_dir / "worktrees" / "dotgitdir"  # a .git DIRECTORY for a pool path
        d.mkdir()
        git("init", "-q", cwd=d)
        self.env.sql("DELETE FROM worktree_pool")
        self.free_row(d)
        self.cfg_sql("worktree_pool_max", "0")
        self.runs()
        self.assertTrue((d / ".git").is_dir())
        self.s_intact(s, snap, head)

    def test_t5_gitdir_at_sibling_admin_refused_by_back_pointer(self):
        s, snap, head = self.sib()
        w = self.stale(6)
        (w / ".git").write_text(f"gitdir: {self.wroot()}/{s.name}\n")
        self.runs()
        self.s_intact(s, snap, head)
        self.assertEqual([r["state"] for r in self.pool()], ["claimed"])

    def test_t6_dotdot_nested_and_outside_admin_refused(self):
        s, snap, head = self.sib()
        out = self.env.home_dir / "outside_admin"
        for n, kind in ((6, "dotdot"), (7, "nested"), (8, "outside")):
            w = self.stale(n)
            if kind == "dotdot":
                g = f"{self.wroot()}/zz/../{s.name}"
            else:
                a = (self.wroot() / "a" / "b") if kind == "nested" else out
                a.mkdir(parents=True)
                (a / "gitdir").write_text(f"{w}/.git\n")
                (a / "commondir").write_text(str(self.repo / ".git") + "\n")
                (a / "HEAD").write_text("ref: refs/heads/x\n")
                g = str(a)
            (w / ".git").write_text(f"gitdir: {g}\n")
        self.runs()
        self.s_intact(s, snap, head)
        self.assertEqual([r["state"] for r in self.pool()], ["claimed"] * 3)

    def test_t7_back_pointer_symlink_or_alias_refused(self):
        s, snap, head = self.sib()
        w6 = self.stale(6)
        a = self.admin_of(w6)
        copy = self.env.home_dir / "gitdir.copy"
        copy.write_text((a / "gitdir").read_text())
        (a / "gitdir").unlink()
        (a / "gitdir").symlink_to(copy)  # admin/gitdir is a symlink
        w7 = self.stale(7)
        alias = self.env.home_dir / "alias_dotgit"
        alias.symlink_to(w7 / ".git")  # a resolved compare accepts this alias of w7/.git
        # w7's own admin stays registered (so `git worktree list` names w7 exactly once); w7/.git is aimed at a second admin
        # whose back pointer is the alias: only the unresolved back-pointer compare (step 9) refuses it
        bad = self.wroot() / "alias_admin"
        bad.mkdir()
        real = self.admin_of(w7)
        for n in ("commondir", "HEAD"):
            (bad / n).write_text((real / n).read_text())
        (bad / "gitdir").write_text(str(alias) + "\n")
        (w7 / ".git").write_text(f"gitdir: {bad}\n")
        self.runs()
        self.s_intact(s, snap, head)
        self.assertEqual([r["state"] for r in self.pool()], ["claimed"] * 2)

    def test_t8_forged_commondir_refused(self):
        s, snap, head = self.sib()
        w = self.stale(6)
        other = self.env.home_dir / "other.git"
        git("init", "-q", "--bare", str(other), cwd=self.env.home_dir)
        (self.admin_of(w) / "commondir").write_text(str(other) + "\n")
        self.runs()
        self.s_intact(s, snap, head)
        self.assertEqual([r["state"] for r in self.pool()], ["claimed"])

    def test_t9_second_admin_for_the_same_path_refused(self):
        # a hand-made admin dir that points back at wt/.git makes `git worktree list` name the path twice: not "exactly one"
        s, snap, head = self.sib()
        w = self.stale(6)
        dup = self.wroot() / "dup"
        dup.mkdir()
        real = self.admin_of(w)
        for n in ("gitdir", "commondir", "HEAD"):
            (dup / n).write_text((real / n).read_text())
        (w / ".git").write_text(f"gitdir: {dup}\n")
        listing = git("worktree", "list", "--porcelain", cwd=self.repo)
        self.assertEqual(listing.count(f"worktree {w}\n"), 2, listing)
        self.runs()
        self.s_intact(s, snap, head)
        self.assertTrue(w.is_dir())

    def test_t10_no_git_call_runs_in_or_names_a_forged_dir(self):
        s, snap, head = self.sib()
        w = self.stale(6)
        (w / ".git").write_text(f"gitdir: {self.wroot()}/{s.name}\n")
        shim = self.env.home / "shim"
        shim.mkdir()
        log = self.env.home / "git-calls.log"
        real = shutil.which("git")
        (shim / "git").write_text(f'#!/bin/sh\nprintf \'%s\\t%s\\n\' "$PWD" "$*" >> "{log}"\nexec {real} "$@"\n')
        (shim / "git").chmod(0o755)
        path = f"{self.env.stub_bin}{os.pathsep}{shim}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
        for flag in ("1", "0"):
            self.cfg_sql("worktree_reuse", flag)
            p = self.ok("clean", agent="zz-test-cleaner", extra_env={"PATH": path})
            self.assertIn("kept: gitdir mismatch", p.stdout)
        calls = [l.split("\t", 1) for l in log.read_text().splitlines()]
        self.assertTrue(calls, "the shim saw no git call: the test would prove nothing")
        for cwd, argv in calls:
            self.assertFalse(cwd == str(w) or cwd.startswith(str(w) + "/"), f"git ran in the forged dir: {cwd}: {argv}")
            self.assertNotIn(str(w), argv, f"a git call named the forged dir: {argv}")
        self.s_intact(s, snap, head)

    def test_t11_one_event_one_message_across_routes_and_dry_run_sends_nothing(self):
        s, snap, head = self.sib()
        w = self.stale(6)  # stale-claim route
        (w / ".git").write_text(f"gitdir: {self.wroot()}/{s.name}\n")
        link = self.env.home_dir / "worktrees" / "link"  # trim route
        link.symlink_to(s)
        self.free_row(link)
        self.cfg_sql("worktree_pool_max", "0")
        p = self.clean("--dry-run")
        self.assertEqual(p.stdout.count("kept: gitdir mismatch"), 2)
        self.assertEqual(self.events("worktree-gitdir-mismatch"), [])
        self.assertEqual(self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'"), [])
        for run in (1, 2):
            self.clean()
            self.assertEqual(len(self.events("worktree-gitdir-mismatch")), 2, f"run {run}")
            self.assertEqual(len(self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'")), 2, f"run {run}")
        self.s_intact(s, snap, head)

    def test_t12_pool_and_clean_code_touches_worktrees_only_through_the_choke_point(self):
        src = (Path(__file__).resolve().parent.parent / "bin" / "factory_cli.py").read_text()
        text = src.splitlines()
        scoped = {"clean_verdict", "_clean_stale_claims", "_clean_pool_trim", "_pool_poolable", "_pool_reset", "cmd_clean"}
        bad = re.compile(r"\b(git_run|_git|cgit)\(\s*t?wt\b|\"worktree\",\s*\"remove\"")
        seen = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name in scoped:
                seen.add(node.name)
                skip = {id(n) for sub in ast.walk(node) if isinstance(sub, ast.FunctionDef) and sub.name == "wgit" for n in ast.walk(sub)}
                for ln in sorted({n.lineno for n in ast.walk(node) if id(n) not in skip and hasattr(n, "lineno")}):
                    self.assertIsNone(bad.search(text[ln - 1]), f"{node.name}:{ln} touches a worktree outside _wt_git/_wt_remove")
        self.assertEqual(seen, scoped)

    def test_merged_clone_is_removed_not_flagged_with_flag_on(self):
        # self-review finding: a per-task clone (.git a directory) must not hit the ownership refusal when pooling is on
        wt = self.env.home_dir / "worktrees" / "G-001-T-0001"
        git("-c", "protocol.file.allow=always", "clone", "-q", "--shared", "--no-checkout", str(self.repo), str(wt), cwd=self.env.home)
        git("remote", "set-url", "origin", str(self.origin), cwd=wt)
        git("fetch", "-q", "origin", cwd=wt)
        git("checkout", "-q", "-b", "factory/t-0001", "origin/main", cwd=wt)
        (wt / "f1").write_text("work\n")
        git("add", "f1", cwd=wt)
        git("-c", "user.name=zz", "-c", "user.email=zz@example.invalid", "commit", "-q", "-m", "work", cwd=wt)
        git("push", "-q", "origin", "factory/t-0001", cwd=wt)
        self.env.seed_task("T-0001", status="done", pr_url=URL % 1)
        self.env.sql("UPDATE tasks SET worktree=?, branch='factory/t-0001' WHERE id='T-0001'", (str(wt),))
        self.env.seed_pr(URL % 1, sha=git("rev-parse", "HEAD", cwd=wt), state="MERGED")
        p = self.clean()
        self.assertNotIn("gitdir mismatch", p.stdout)
        self.assertFalse(wt.exists())
        self.assertEqual(self.pool(), [])
        self.assertEqual(self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'"), [])


if __name__ == "__main__":
    unittest.main()
