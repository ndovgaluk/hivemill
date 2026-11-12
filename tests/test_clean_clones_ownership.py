import hashlib
import os
import unittest

from harness import git
from test_clean_clones import CloneCleanBase

ALERT = "SELECT 1 FROM events WHERE action='worktree-gitdir-mismatch'"
MSGS = "SELECT 1 FROM messages WHERE recipient='director' AND subject LIKE 'worktree % has a forged .git pointer'"


class CloneOwnershipTests(CloneCleanBase):
    def sibling(self):
        """Clone S next to the task clone; returns (path, HEAD sha, index sha256)."""
        s = self.wts / "sibling-S"
        git("-c", "protocol.file.allow=always", "clone", "-q", "--shared", str(self.repo), str(s), cwd=self.env.home)
        return s, *self.snap(s)

    @staticmethod
    def snap(s):
        return git("rev-parse", "HEAD", cwd=s), hashlib.sha256((s / ".git" / "index").read_bytes()).hexdigest()

    def assert_kept_once(self, wt, s, head, idx):
        p = self.clean()
        self.assertIn("kept: gitdir mismatch", p.stdout)
        self.assertTrue(os.path.lexists(wt))
        self.assertEqual(len(self.env.sql(ALERT)), 1)
        self.assertEqual(len(self.env.sql(MSGS)), 1)
        self.assertEqual(self.snap(s), (head, idx))
        self.clean()  # second run: kept again, no new event or message
        self.assertEqual(len(self.env.sql(ALERT)), 1)
        self.assertEqual(len(self.env.sql(MSGS)), 1)
        self.assertEqual(self.snap(s), (head, idx))
        self.assertEqual(len(self.env.sql("SELECT 1 FROM events WHERE action='cleaned'")), 0)

    def test_commondir_file_kept(self):
        wt, _ = self.clone_task()
        s, head, idx = self.sibling()
        (wt / ".git" / "commondir").write_text(str(s / ".git") + "\n")
        self.assert_kept_once(wt, s, head, idx)

    def test_gitdir_file_kept(self):
        wt, _ = self.clone_task()
        s, head, idx = self.sibling()
        (wt / ".git" / "gitdir").write_text(str(s / ".git") + "\n")
        self.assert_kept_once(wt, s, head, idx)

    def test_symlinked_clone_dir_kept(self):
        wt, _ = self.clone_task()
        s, head, idx = self.sibling()
        os.rename(wt, self.env.home / "moved")
        os.symlink(s, wt)  # the task path now points at sibling S
        self.assert_kept_once(wt, s, head, idx)
        self.assertTrue(wt.is_symlink())

    def test_symlinked_dotgit_kept(self):
        wt, _ = self.clone_task()
        s, head, idx = self.sibling()
        os.rename(wt / ".git", self.env.home / "moved-git")
        os.symlink(s / ".git", wt / ".git")
        self.assert_kept_once(wt, s, head, idx)

    def test_benign_clone_still_removed(self):
        wt, _ = self.clone_task()
        self.assertIn("1 removed", self.clean().stdout)
        self.assertFalse(wt.exists())
        self.assertEqual(len(self.env.sql(ALERT)), 0)


if __name__ == "__main__":
    unittest.main()
