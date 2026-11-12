import importlib.machinery
import importlib.util
import os
import unittest

from harness import FACTORY_SRC, FactoryTestCase, git


def load_factory(home):
    old = os.environ.get("FACTORY_HOME")
    os.environ["FACTORY_HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader("factory_pool_states_test", str(FACTORY_SRC))
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        return mod
    finally:
        if old is None:
            os.environ.pop("FACTORY_HOME", None)
        else:
            os.environ["FACTORY_HOME"] = old

COLUMNS = ["path", "project_id", "state", "task_id", "reset_ok", "claimed_at", "released_at"]


class WorktreeReuseConfigTests(FactoryTestCase):
    """worktree_reuse / worktree_pool_max config keys and the worktree_pool table (no reader yet)."""

    def setUp(self):
        super().setUp()
        self.env.seed_agent("zz-test-director", "director")

    def cfg(self, *args, code=0):
        p = self.env.run("config", *args, agent="zz-test-director")
        self.assertEqual(p.returncode, code, f"{args}: rc={p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    def test_defaults_off(self):
        lines = self.cfg().stdout.splitlines()
        self.assertIn("worktree_reuse = 0", lines)
        self.assertIn("worktree_pool_max = 2", lines)

    def test_reuse_validation(self):
        for bad in ("2", "yes", ""):
            p = self.cfg("worktree_reuse", bad, code=2)
            self.assertIn("worktree_reuse must be 0 or 1", p.stderr)
        self.cfg("worktree_reuse", "1")
        self.assertIn("worktree_reuse = 1", self.cfg().stdout.splitlines())
        self.cfg("worktree_reuse", " 0 ")
        self.assertIn("worktree_reuse = 0", self.cfg().stdout.splitlines())

    def test_pool_max_validation(self):
        for bad in ("-1", "abc", "51", "", "1.5"):
            p = self.cfg("worktree_pool_max", bad, code=2)
            self.assertIn("worktree_pool_max must be an integer 0..50", p.stderr)
        for good in ("0", "5", "50"):
            self.cfg("worktree_pool_max", good)
            self.assertIn(f"worktree_pool_max = {good}", self.cfg().stdout.splitlines())

    def test_table_on_fresh_init(self):
        con = self.env.db()
        try:
            cols = [r["name"] for r in con.execute("PRAGMA table_info(worktree_pool)")]
            self.assertEqual(cols, COLUMNS)
            sql = con.execute("SELECT sql FROM sqlite_master WHERE name='worktree_pool'").fetchone()[0]
            self.assertNotIn("CHECK", sql.upper())
            self.assertEqual(load_factory(self.env.home_dir).WORKTREE_POOL_STATES, ("free", "claimed"))
            con.execute("INSERT INTO worktree_pool(path, project_id, state) VALUES('/p','x','free')")
            self.assertEqual(con.execute("SELECT reset_ok FROM worktree_pool").fetchone()[0], 0)
        finally:
            con.close()

    def test_migration_idempotent(self):
        self.env.seed_project()
        self.env.sql("DROP TABLE worktree_pool")
        self.ok("config")
        self.ok("config")
        cols = [r["name"] for r in self.env.sql("PRAGMA table_info(worktree_pool)")]
        self.assertEqual(cols, COLUMNS)
        self.assertEqual([r["id"] for r in self.env.sql("SELECT id FROM projects")], ["zz-test-proj"])
        idx = [r["name"] for r in self.env.sql("PRAGMA index_list(worktree_pool)")]
        self.assertIn("worktree_pool_proj", idx)

    def test_state_dump_includes_table(self):
        e = self.env
        e.seed_project()
        bare = e.home / "origin.git"
        git("init", "-q", "--bare", "-b", "main", str(bare), cwd=e.home)
        git("remote", "add", "origin", str(bare), cwd=e.home_dir)
        self.ok("export", "--no-push")
        dump = (e.home_dir / "state" / "factory.sql").read_text()
        self.assertIn("CREATE TABLE worktree_pool", dump)


if __name__ == "__main__":
    unittest.main()
