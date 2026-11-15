"""HM-32: config coder_self_review (on|off). Off adds one sentence to a newly spawned coder's kickoff; anything else is on."""
import unittest

from harness import FactoryTestCase

KEY = "coder_self_review"
LINE = ('coder_self_review is off: skip step 7 (skill coder-skills:self-review), start no review subagent or workflow, '
        'and put the line "Self-review: off (config coder_self_review)" in the PR body.')


class Kickoff(FactoryTestCase):
    def kick(self, role="coder", prompt="base"):
        with self.env.load_factory() as f:
            return f.coder_self_review_kickoff(f.db(), role, prompt)

    def test_default_is_on_on_a_fresh_home(self):
        p = self.ok("config", KEY)
        self.assertEqual(p.stdout.strip(), "on")

    def test_off_appends_the_sentence(self):
        self.ok("config", KEY, "off")
        self.assertEqual(self.kick(), f"base {LINE}")

    def test_on_unset_and_unknown_leave_the_prompt_alone(self):
        self.assertEqual(self.kick(), "base")
        self.ok("config", KEY, "on")
        self.assertEqual(self.kick(), "base")
        self.env.sql("UPDATE config SET value='maybe' WHERE key=?", (KEY,))
        self.assertEqual(self.kick(), "base")

    def test_other_roles_are_unchanged_when_off(self):
        self.ok("config", KEY, "off")
        for role in ("reviewer", "qa", "lead"):
            self.assertEqual(self.kick(role), "base")

    def test_empty_prompt_gives_the_sentence_alone(self):
        self.ok("config", KEY, "off")
        self.assertEqual(self.kick(prompt=""), LINE)


class SpawnedKickoff(FactoryTestCase):
    def test_coder_kickoff_holds_both_sentences_with_ci_handoff(self):
        e = self.env
        e.seed_goal()
        e.seed_task()
        self.ok("config", "review_autospawn", "on")
        self.ok("config", "coder_ci_handoff", "resume")
        self.ok("config", KEY, "off")
        p = e.run("spawn", "coder", "--goal", "G-001", "--task", "T-0001", "--name", "zz-test-coder")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        body = e.sql("SELECT body FROM messages WHERE subject LIKE 'kickoff: coder%'")[0]["body"]
        self.assertIn("do not wait for CI", body)
        self.assertIn(LINE, body)

    def test_on_adds_no_sentence(self):
        e = self.env
        e.seed_goal()
        e.seed_task()
        p = e.run("spawn", "coder", "--goal", "G-001", "--task", "T-0001", "--name", "zz-test-coder")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        body = e.sql("SELECT body FROM messages WHERE subject LIKE 'kickoff: coder%'")[0]["body"]
        self.assertNotIn("coder_self_review is off", body)


if __name__ == "__main__":
    unittest.main()
