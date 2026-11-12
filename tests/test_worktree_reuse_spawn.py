"""G-001 T-0003: `factory spawn coder` with worktree_reuse=1 claims and resets a pooled worktree.
Real CLI (harness herdr stub), real git repos (bare origin + home checkout), temp FACTORY_HOME. A "freed" worktree is
made by make_pooled(): real `git worktree add`, then a worktree_pool row (the real release path is a later task)."""
import ast
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import unittest
from pathlib import Path

from harness import FactoryTestCase, git

MARK = "# factory pre-push public-text guard (G-021 T-0696)"


class ReuseBase(FactoryTestCase):
    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_project()
        e.seed_goal(project="zz-test-proj", title="zz-test reuse goal")
        e.seed_team(lead="zz-lead")
        e.seed_agent("zz-director", "director")
        self.h = e.home_dir
        self.bare = e.home / "origin.git"
        git("init", "-q", "--bare", "-b", "main", str(self.bare), cwd=e.home)
        git("remote", "add", "origin", str(self.bare), cwd=self.h)
        git("commit", "-q", "--allow-empty", "-m", "base", cwd=self.h)
        git("push", "-q", "-u", "origin", "main", cwd=self.h)
        e.sql("UPDATE projects SET repo_path=? WHERE id='zz-test-proj'", (str(self.h),))
        for t in ("T-0001", "T-0002", "T-0003"):
            e.seed_task(tid=t, goal="G-001", status="in_progress", team="g-001-a", pr_url=None)
        self.ok("config", "worktree_reuse", "1", agent="zz-director")

    def make_pooled(self, task="T-0001", state="free"):
        """The worktree of `task` as it is when freed: branch with a pushed-in commit, node_modules ignored."""
        wt = self.h / "worktrees" / f"G-001-{task}"
        br = f"factory/{task.lower()}"
        git("worktree", "add", "-q", "-B", br, str(wt), "origin/main", cwd=self.h)
        (self.h / ".git" / "info").mkdir(exist_ok=True)
        (self.h / ".git" / "info" / "exclude").write_text("node_modules/\n")  # ignored in every worktree of the repo
        git("commit", "-q", "--allow-empty", "-m", "task work", cwd=wt)
        git("push", "-q", "origin", f"HEAD:refs/heads/{br}", cwd=wt)
        (wt / "node_modules").mkdir()
        (wt / "node_modules" / "x.js").write_text("module.exports = 1;\n")
        self.env.sql("INSERT INTO worktree_pool(path,project_id,state,task_id,reset_ok,released_at) VALUES(?,?,?,?,0,?)",
                     (str(wt), "zz-test-proj", state, None if state == "free" else task, "2026-01-01T00:00:00+00:00"))
        # main moves on after the worktree was freed: reuse must land on the new origin/main
        git("commit", "-q", "--allow-empty", "-m", "newer", cwd=self.h)
        git("push", "-q", "origin", "main", cwd=self.h)
        return wt

    def gitdir(self, wt):
        return Path(wt, git("rev-parse", "--git-dir", cwd=wt)).resolve()

    def spawn(self, task="T-0002", name=None, extra_env=None):
        return self.env.run("spawn", "coder", "--goal", "G-001", "--team", "g-001-a", "--task", task,
                            "--name", name or f"zz-coder-{task.lower()}", agent="zz-director", extra_env=extra_env)

    def spawn_ok(self, *a, **k):
        p = self.spawn(*a, **k)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def task(self, tid="T-0002"):
        return self.env.sql("SELECT * FROM tasks WHERE id=?", (tid,))[0]

    def pool(self):
        return self.env.sql("SELECT * FROM worktree_pool ORDER BY path")

    def events(self, action):
        return self.env.sql("SELECT * FROM events WHERE action=?", (action,))

    def fresh(self, task="T-0002"):
        return str(self.h / "worktrees" / f"G-001-{task}")


class Reuse(ReuseBase):
    def test_flag_off_makes_a_fresh_worktree(self):  # acceptance 1
        P = self.make_pooled()
        self.ok("config", "worktree_reuse", "0", agent="zz-director")
        self.spawn_ok()
        self.assertEqual(self.task()["worktree"], self.fresh())
        row = self.pool()[0]
        self.assertEqual((row["path"], row["state"], row["task_id"]), (str(P), "free", None))
        self.assertEqual(self.events("worktree-claimed"), [])

    def test_reuse_keeps_ignored_files_and_resets_branch(self):  # acceptance 2
        P = self.make_pooled()
        self.spawn_ok()
        self.assertEqual(self.task()["worktree"], str(P))
        self.assertEqual(self.task()["branch"], "factory/t-0002")
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=P), "factory/t-0002")
        self.assertEqual(git("rev-parse", "HEAD", cwd=P), git("rev-parse", "origin/main", cwd=self.h))
        self.assertEqual((P / "node_modules" / "x.js").read_text(), "module.exports = 1;\n")
        row = self.pool()[0]
        self.assertEqual((row["state"], row["task_id"], row["reset_ok"]), ("claimed", "T-0002", 1))
        self.assertEqual(len(self.events("worktree-reused")), 1)
        self.assertFalse((self.h / "worktrees" / "G-001-T-0002").exists())

    def test_isolation_from_the_previous_task(self):  # acceptance 3
        P = self.make_pooled()
        (P / "tracked.txt").write_text("v1\n")
        git("add", "tracked.txt", cwd=P)
        git("commit", "-q", "-m", "tracked", cwd=P)
        (P / "tracked.txt").write_text("edited\n")
        (P / "staged.txt").write_text("s\n")
        git("add", "staged.txt", cwd=P)
        (P / "stray.txt").write_text("x\n")
        (P / "junk").mkdir()
        (P / "junk" / "f").write_text("x\n")
        gd = self.gitdir(P)
        (gd / "config.worktree").write_text("[user]\n\tname = prev\n")
        self.spawn_ok()
        self.assertEqual(git("status", "--porcelain", "--untracked-files=all", cwd=P), "")
        self.assertFalse((P / "stray.txt").exists())
        self.assertFalse((P / "junk").exists())
        self.assertFalse((P / "tracked.txt").exists())
        self.assertFalse((gd / "config.worktree").exists())
        self.assertTrue((P / "node_modules" / "x.js").exists())

    def test_per_worktree_leftovers_removed_and_hook_installed(self):  # acceptance 4 (and 5: harmless config passes the guard)
        P = self.make_pooled()
        gd = self.gitdir(P)
        (gd / "MERGE_HEAD").write_text(git("rev-parse", "HEAD", cwd=P) + "\n")
        (gd / "BISECT_LOG").write_text("x\n")
        (gd / "rebase-merge").mkdir()
        git("update-ref", "refs/bisect/bad", "HEAD", cwd=P)
        git("update-ref", "refs/worktree/mine", "HEAD", cwd=P)
        (gd / "config.worktree").write_text("[user]\n\tname = prev\n")
        self.spawn_ok()
        for n in ("MERGE_HEAD", "BISECT_LOG", "rebase-merge"):
            self.assertFalse((gd / n).exists(), n)
        self.assertEqual(git("for-each-ref", "refs/bisect", "refs/worktree", cwd=P), "")
        hook = self.h / ".git" / "hooks" / "pre-push"
        self.assertIn(MARK, hook.read_text())

    def test_branch_already_exists_is_reset(self):  # acceptance 12
        P = self.make_pooled()
        old = git("rev-parse", "HEAD~1", cwd=self.h)
        git("branch", "factory/t-0002", old, cwd=self.h)
        self.spawn_ok()
        self.assertEqual(git("rev-parse", "factory/t-0002", cwd=P), git("rev-parse", "origin/main", cwd=self.h))

    def test_task_clones_win(self):  # acceptance 8
        P = self.make_pooled()
        self.ok("config", "task_clones", "1", agent="zz-director")
        self.spawn_ok()
        wt = Path(self.task()["worktree"])
        self.assertEqual(wt, self.h / "worktrees" / "G-001-T-0002")
        self.assertTrue((wt / ".git").is_dir())
        self.assertEqual(self.pool()[0]["state"], "free")
        self.assertEqual(self.pool()[0]["path"], str(P))

    def test_broken_pool_dir_falls_back_to_fresh(self):  # acceptance 11
        P = self.make_pooled()
        shutil.rmtree(P)
        self.spawn_ok()
        self.assertEqual(self.task()["worktree"], self.fresh())
        self.assertEqual(self.pool(), [])
        ev = self.events("worktree-reuse-failed")
        self.assertEqual(len(ev), 1)
        self.assertEqual(json.loads(ev[0]["detail"])["path"], str(P))

    def test_nested_repo_and_sequencer_leftovers_removed(self):  # acceptance 17
        P = self.make_pooled()
        gd = self.gitdir(P)
        (P / "sub").mkdir()
        git("init", "-q", str(P / "sub"), cwd=P)
        (P / "sub" / "f.txt").write_text("x\n")
        (gd / "sequencer").mkdir()
        (gd / "sequencer" / "todo").write_text("pick abc\n")
        self.spawn_ok()
        self.assertEqual(self.task()["worktree"], str(P))
        self.assertFalse((P / "sub").exists())
        self.assertFalse((gd / "sequencer").exists())
        self.assertEqual(git("status", "--porcelain", "--untracked-files=all", cwd=P), "")
        self.assertTrue((P / "node_modules" / "x.js").exists())

    # acceptance 16 (reviewer B1, M125/M128): every forged pool row is refused by the shared helper, sibling S stays intact
    def forge_case(self, forge):
        S = self.make_pooled("T-0003", state="claimed")  # a live worktree of another task
        P = self.make_pooled("T-0001")
        self.env.sql("UPDATE worktree_pool SET task_id='T-0003', reset_ok=1 WHERE path=?", (str(S),))
        sgd = self.gitdir(S)
        (sgd / "MERGE_HEAD").write_text(git("rev-parse", "HEAD", cwd=S) + "\n")
        (S / "wip.txt").write_text("live work\n")

        def snap():
            h = lambda n: hashlib.sha256((sgd / n).read_bytes()).hexdigest()
            return (h("index"), h("HEAD"), git("status", "--porcelain", cwd=S), (sgd / "MERGE_HEAD").exists())

        before = snap()
        path = forge(P, S, sgd)
        p = self.spawn_ok()
        self.assertEqual(self.task()["worktree"], self.fresh(), p.stdout)
        self.assertEqual(snap(), before)
        self.assertTrue((S / "wip.txt").exists() and sgd.is_dir())
        self.assertTrue(os.path.lexists(path), "the pooled dir must be kept")
        row = [r for r in self.pool() if r["path"] == str(path)]
        self.assertEqual([(r["state"], r["task_id"]) for r in row], [("free", None)])
        self.assertEqual(len(self.events("worktree-gitdir-mismatch")), 1)
        self.assertEqual(len(self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'")), 1)

    def test_a_gitdir_redirect_to_a_sibling_is_refused(self):
        def forge(P, S, sgd):
            (P / ".git").write_text(f"gitdir: {sgd}\n")
            return P
        self.forge_case(forge)

    def test_b_symlink_to_a_sibling_is_refused(self):
        def forge(P, S, sgd):
            shutil.move(str(P), str(self.h / "elsewhere"))
            P.symlink_to(S)
            return P
        self.forge_case(forge)

    def test_c_symlinked_parent_is_refused(self):
        def forge(P, S, sgd):
            real = self.h / "realdir"
            real.mkdir()
            (self.h / "worktrees" / "linkdir").symlink_to(real)
            moved = real / P.name
            shutil.move(str(P), str(moved))
            q = self.h / "worktrees" / "linkdir" / P.name
            self.env.sql("UPDATE worktree_pool SET path=? WHERE path=?", (str(q), str(P)))
            return q
        self.forge_case(forge)

    def test_d_dotgit_symlink_is_refused(self):
        def forge(P, S, sgd):
            (P / ".git").unlink()
            (P / ".git").symlink_to(S / ".git")
            return P
        self.forge_case(forge)

    # acceptance 16 / C4: _pool_drop itself on a mismatch (crash-recovery path: claimed row, reset_ok=0, then P is forged)
    def drop_case(self, forge):
        S = self.make_pooled("T-0003", state="claimed")
        P = self.make_pooled("T-0001", state="claimed")
        self.env.sql("UPDATE worktree_pool SET task_id='T-0002', reset_ok=0 WHERE path=?", (str(P),))
        self.env.sql("UPDATE worktree_pool SET task_id='T-0003', reset_ok=1 WHERE path=?", (str(S),))
        self.env.sql("UPDATE tasks SET worktree=?, branch='factory/t-0002' WHERE id='T-0002'", (str(P),))
        sgd = self.gitdir(S)
        (S / "wip.txt").write_text("live work\n")
        h = lambda n: hashlib.sha256((sgd / n).read_bytes()).hexdigest()
        before = (h("index"), h("HEAD"), git("status", "--porcelain", cwd=S))
        forge(P, S, sgd)
        self.spawn_ok()
        self.assertEqual(self.task()["worktree"], self.fresh())
        self.assertEqual((h("index"), h("HEAD"), git("status", "--porcelain", cwd=S)), before)
        self.assertTrue((S / "wip.txt").exists() and sgd.is_dir())
        self.assertTrue(os.path.lexists(P), "the pooled dir must be kept")
        self.assertEqual([(r["state"], r["task_id"]) for r in self.pool() if r["path"] == str(P)], [("free", None)])
        self.assertTrue([e for e in self.events("worktree-reuse-failed") if "kept:" in e["detail"]], "_pool_drop must have run")
        self.assertGreaterEqual(len(self.events("worktree-gitdir-mismatch")), 1)
        self.assertEqual(len(self.env.sql("SELECT * FROM messages WHERE subject LIKE '%forged .git pointer%'")), 1)

    def test_drop_keeps_a_redirected_worktree(self):
        def forge(P, S, sgd):
            (P / ".git").write_text(f"gitdir: {sgd}\n")
        self.drop_case(forge)

    def test_drop_keeps_a_symlinked_worktree(self):
        def forge(P, S, sgd):
            shutil.move(str(P), str(self.h / "elsewhere"))
            P.symlink_to(S)
        self.drop_case(forge)

    def test_pool_functions_touch_worktrees_only_through_the_choke_point(self):  # acceptance 19 / spec 6 (T12 scope)
        src = (Path(__file__).resolve().parent.parent / "bin" / "factory_cli.py").read_text()
        text = src.splitlines()
        scoped = {"claim_pooled_worktree", "reset_pooled_worktree", "_pool_drop", "_pool_release_claim"}
        bad = re.compile(r"\b(git_run|_git|cgit)\(\s*t?(wt|p)\b|\"worktree\",\s*\"remove\"|rmtree\(wt")
        seen = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name in scoped:
                seen.add(node.name)
                for ln in sorted({n.lineno for n in ast.walk(node) if hasattr(n, "lineno")}):
                    self.assertIsNone(bad.search(text[ln - 1]), f"{node.name}:{ln} touches a worktree outside _wt_git/_wt_remove")
        self.assertEqual(seen, scoped)
        self.assertEqual(src.count("def worktree_owns_gitdir"), 1)
        self.assertEqual(src.count("def _wt_git"), 1)

    def test_consumers_see_the_claimed_path(self):  # acceptance 9
        P = self.make_pooled()
        self.spawn_ok()
        with self.env.load_factory() as mod:
            con = mod.db()
            self.assertEqual(mod.prepare_worktree(con, "T-0002", "qa"), str(P))  # verifiers work in the claimed path
            self.assertEqual(con.execute("SELECT worktree FROM tasks WHERE id='T-0002'").fetchone()["worktree"], str(P))
            mod.coder_done_findings(con, {"task_id": "T-0002"}, True)


class Guard(ReuseBase):
    def assert_refused(self, P):
        p = self.spawn()
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        self.assertIn("spawn refused: git config in", p.stderr)
        row = self.pool()[0]
        self.assertEqual((row["state"], row["task_id"]), ("free", None))
        t = self.task()
        self.assertIsNone(t["worktree"])
        self.assertTrue(P.exists())

    def test_refused_key_in_worktree_config(self):  # acceptance 6a
        P = self.make_pooled()
        # the repo-level guard reads worktrees/*/config.worktree too, so this is refused before any claim
        gd = self.gitdir(P)
        (gd / "config.worktree").write_text("[core]\n\tfsmonitor = /bin/true\n")
        self.assert_refused(P)
        self.assertEqual((gd / "config.worktree").read_text(), "[core]\n\tfsmonitor = /bin/true\n")

    def test_refused_key_in_common_config(self):  # acceptance 6b
        P = self.make_pooled()
        git("config", "core.fsmonitor", "/bin/true", cwd=self.h)
        self.assert_refused(P)

    def test_guard_refusal_after_claim_rolls_back(self):  # acceptance 6c, 5 (guard called with P before checkout)
        P = self.make_pooled()
        with self.env.load_factory() as mod:
            real, seen = mod.git_config_guard, []

            def guard(con, repo, always_event=False):
                seen.append(str(repo))
                return False if str(repo) == str(P) else real(con, repo, always_event)

            mod.git_config_guard = guard
            con = mod.db()
            with self.assertRaises(SystemExit) as cm:
                mod.prepare_worktree(con, "T-0002", "coder")
            self.assertEqual(cm.exception.code, 4)
            self.assertIn(str(P), seen)
        row = self.pool()[0]
        self.assertEqual((row["state"], row["task_id"]), ("free", None))
        t = self.task()
        self.assertEqual((t["worktree"], t["branch"]), (None, None))
        self.assertTrue(P.exists())
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=P), "factory/t-0001")  # no checkout happened


class Claim(ReuseBase):
    def conn(self, timeout=5):
        con = sqlite3.connect(self.env.db_path, timeout=timeout, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con

    def test_claim_row_is_won_by_exactly_one(self):  # acceptance 7 test A
        P = self.make_pooled()
        a, b = self.conn(), self.conn()
        with self.env.load_factory() as mod:
            for c in (a, b):
                self.assertEqual(c.execute("SELECT path FROM worktree_pool WHERE state='free'").fetchone()["path"], str(P))
            won = [mod._claim_row(a, str(P), "T-0002", "b2"), mod._claim_row(b, str(P), "T-0003", "b3")]
        self.assertEqual(sorted(won), [0, 1])
        self.assertEqual(self.pool()[0]["task_id"], "T-0002")

    def test_claim_takes_the_write_lock(self):  # acceptance 7 test B
        P = self.make_pooled()
        x, y = self.conn(), self.conn(timeout=0)
        y.execute("PRAGMA busy_timeout=0")
        x.execute("BEGIN IMMEDIATE")
        with self.env.load_factory() as mod:
            with self.assertRaises(sqlite3.OperationalError) as cm:
                mod.claim_pooled_worktree(y, "zz-test-proj", "T-0003", "factory/t-0003")
            self.assertIn("locked", str(cm.exception))
            # the lock is taken at BEGIN, before any row is read: an empty pool raises too (a plain BEGIN would not)
            with self.assertRaises(sqlite3.OperationalError):
                mod.claim_pooled_worktree(y, "zz-no-such-project", "T-0003", "factory/t-0003")
            x.execute("ROLLBACK")
            self.assertEqual(mod.claim_pooled_worktree(y, "zz-test-proj", "T-0003", "factory/t-0003"), str(P))
            self.assertEqual(y.execute("SELECT worktree FROM tasks WHERE id='T-0003'").fetchone()["worktree"], str(P))

    def test_claim_inside_transaction_dies(self):
        self.make_pooled()
        y = self.conn()
        y.execute("BEGIN")
        with self.env.load_factory() as mod:
            with self.assertRaises(SystemExit):
                mod.claim_pooled_worktree(y, "zz-test-proj", "T-0003", "factory/t-0003")

    def test_two_real_spawns_never_share_a_row(self):  # acceptance 7 smoke C
        for i in range(5):
            if i:
                self.tearDown_env_and_rebuild()
            P = self.make_pooled()
            for t in ("T-0002", "T-0003"):
                shutil.copy(self.env.herdr_state, self.env.herdr_state.with_name(f"herdr-{t}.json"))
            out = {}

            def go(t):
                out[t] = self.spawn(t, extra_env={"FAKE_HERDR_STATE": str(self.env.herdr_state.with_name(f"herdr-{t}.json"))})

            th = [threading.Thread(target=go, args=(t,)) for t in ("T-0002", "T-0003")]
            [x.start() for x in th]
            [x.join() for x in th]
            for t, p in out.items():
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            paths = sorted(self.task(t)["worktree"] for t in ("T-0002", "T-0003"))
            self.assertEqual(paths.count(str(P)), 1)
            self.assertEqual(len([r for r in self.pool() if r["state"] == "claimed"]), 1)

    def tearDown_env_and_rebuild(self):
        self.env.cleanup()
        self.setUp()


class Crash(ReuseBase):
    def test_unfinished_reset_is_redone_on_respawn(self):  # acceptance 10a
        P = self.make_pooled(state="claimed", task="T-0002")
        self.env.sql("UPDATE tasks SET worktree=?, branch='factory/t-0002' WHERE id='T-0002'", (str(P),))
        (P / "stray.txt").write_text("x\n")
        self.spawn_ok()
        self.assertFalse((P / "stray.txt").exists())
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=P), "factory/t-0002")
        self.assertEqual(git("rev-parse", "HEAD", cwd=P), git("rev-parse", "origin/main", cwd=self.h))
        self.assertEqual(self.pool()[0]["reset_ok"], 1)

    def test_crash_recovery_refuses_a_planted_repo_config_before_fetching(self):  # self-review: guard before fetch
        P = self.make_pooled(state="claimed", task="T-0002")
        self.env.sql("UPDATE tasks SET worktree=?, branch='factory/t-0002' WHERE id='T-0002'", (str(P),))
        (P / "stray.txt").write_text("x\n")
        git("config", "core.fsmonitor", "/bin/true", cwd=self.h)
        p = self.spawn()
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        self.assertIn("spawn refused: git config in", p.stderr)
        self.assertTrue((P / "stray.txt").exists())
        self.assertEqual(self.pool()[0]["reset_ok"], 0)

    def test_finished_reset_keeps_the_coders_commit(self):  # acceptance 10b
        P = self.make_pooled()
        self.spawn_ok()
        (P / "w.txt").write_text("work\n")
        git("add", "w.txt", cwd=P)
        git("commit", "-q", "-m", "coder work", cwd=P)
        (P / "u.txt").write_text("uncommitted\n")
        self.spawn_ok(name="zz-coder-again")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=P), "coder work")
        self.assertTrue((P / "u.txt").exists())


if __name__ == "__main__":
    unittest.main()


class Lifecycle(ReuseBase):
    """G-001 SC2/SC5/SC6: the whole reuse lifecycle through the real `factory spawn` / `factory clean` CLI and real git."""

    def setUp(self):
        super().setUp()
        e = self.env
        (self.h / ".gitignore").write_text("node_modules/\n")
        git("add", ".gitignore", cwd=self.h)
        git("commit", "-q", "-m", "ignore node_modules", cwd=self.h)
        git("push", "-q", "origin", "main", cwd=self.h)
        e.seed_task(tid="T-0004", goal="G-001", status="in_progress", team="g-001-a", pr_url=None)
        e.seed_agent("zz-test-cleaner", "cleaner", goal="G-001")

    def free_count(self):
        return self.env.sql("SELECT count(*) AS n FROM worktree_pool WHERE state='free'")[0]["n"]

    def finish(self, task, wt, merged_file):
        """The worker commits and pushes, the PR is merged into the bare origin's main, the task is done."""
        tid = task.lower()
        (wt / merged_file).write_text(f"{task}\n")
        git("add", merged_file, cwd=wt)
        git("commit", "-q", "-m", f"work {task}", cwd=wt)
        git("push", "-q", "origin", f"HEAD:refs/heads/factory/{tid}", cwd=wt)
        sha = git("rev-parse", "HEAD", cwd=wt)
        git("fetch", "-q", "origin", cwd=self.h)
        git("merge", "-q", "--no-ff", "-m", f"merge {task}", f"origin/factory/{tid}", cwd=self.h)
        git("push", "-q", "origin", "main", cwd=self.h)
        url = f"https://github.com/zz-test/repo/pull/{int(task[2:])}"
        self.env.seed_pr(url, sha=sha, state="MERGED")
        self.env.sql("UPDATE tasks SET status='done', pr_url=? WHERE id=?", (url, task))
        self.env.sql("UPDATE agents SET status='exited' WHERE name=?", (f"zz-coder-{tid}",))  # the worker pane is gone

    def test_lifecycle(self):
        # a. flag on, cap 1 (setUp turned the flag on; set the cap)
        self.ok("config", "worktree_reuse", "1", agent="zz-director")
        self.ok("config", "worktree_pool_max", "1", agent="zz-director")
        # b. fresh worktree P1 with an ignored dependency
        self.spawn_ok("T-0001")
        P1 = Path(self.task("T-0001")["worktree"])
        self.assertEqual(str(P1), self.fresh("T-0001"))
        (P1 / "node_modules").mkdir()
        (P1 / "node_modules" / "dep.js").write_text("module.exports = 1;\n")
        self.finish("T-0001", P1, "one.txt")
        # c. clean pools it
        self.ok("clean", agent="zz-test-cleaner")
        self.assertEqual([(r["path"], r["state"]) for r in self.pool()], [(str(P1.resolve()), "free")])
        self.assertTrue(P1.exists())
        # d. the next task gets P1 back, on its own branch at the new origin/main
        self.spawn_ok("T-0002")
        self.assertEqual(Path(self.task("T-0002")["worktree"]).resolve(), P1.resolve())
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=P1), "factory/t-0002")
        git("fetch", "-q", "origin", cwd=self.h)
        self.assertEqual(git("rev-parse", "HEAD", cwd=P1), git("rev-parse", "origin/main", cwd=self.h))
        self.assertTrue((P1 / "node_modules" / "dep.js").exists())
        self.assertEqual(git("status", "--porcelain", "--untracked-files=all", cwd=P1), "")
        # e. P1 is claimed, so a concurrent task gets a fresh worktree
        self.spawn_ok("T-0003")
        P3 = Path(self.task("T-0003")["worktree"])
        self.assertNotEqual(P3.resolve(), P1.resolve())
        self.assertEqual(str(P3), self.fresh("T-0003"))
        # f. both finish; clean keeps exactly one free worktree, removes the other, and no claimed row is lost
        self.finish("T-0002", P1, "two.txt")
        self.finish("T-0003", P3, "three.txt")
        self.ok("clean", agent="zz-test-cleaner")
        self.assertEqual(self.free_count(), 1)
        self.assertEqual(len(self.pool()), 1)
        self.assertEqual(self.env.sql("SELECT count(*) AS n FROM worktree_pool WHERE state='claimed'")[0]["n"], 0)
        self.assertEqual(sum(p.exists() for p in (P1, P3)), 1)
        # g. flag off: clean empties the pool; the next spawn is a fresh worktree
        self.ok("config", "worktree_reuse", "0", agent="zz-director")
        self.ok("clean", agent="zz-test-cleaner")
        self.assertEqual(self.free_count(), 0)
        self.assertEqual(self.pool(), [])
        self.assertFalse(P1.exists() or P3.exists())
        self.spawn_ok("T-0004")
        self.assertTrue(self.task("T-0004")["worktree"].endswith("/worktrees/G-001-T-0004"))
        self.assertTrue(Path(self.task("T-0004")["worktree"]).is_dir())

