"""HM-52: config gate_ignore_pending_ci. In local gate mode (projects.gate_cmd set) with the key on, the head's local gate
run is the one test run: the judge merges on its pass while GitHub's checks are still running (a finished red check still
refuses), the first review starts on its pass, a failed run restarts the coder with the failing tests, and the coder's
pre-check is met by its pass instead of a ci/affected.py run. Outside local mode, or with the key off, nothing changes."""
import json
import unittest

import test_ci_handoff as tch
import test_ci_handoff_red as tcr
import test_gate_integration as tgi
import test_prcheck as tp
from harness import PR_URL
from test_gate_integration import runs, seed_run

KEY = "gate_ignore_pending_ci"
PENDING = [{"name": "unittest", "status": "IN_PROGRESS", "conclusion": ""}]
FINISHED_RED = [{"name": "unittest", "status": "COMPLETED", "conclusion": "FAILURE"}]


@tch.own_tests_only
class JudgeIgnoresPendingChecks(tgi.LocalJudge):
    def setUp(self):
        super().setUp()
        self.env.seed_pr(checks=PENDING)  # GitHub's run has not finished

    def require_unittest(self):
        """T-1634 (upstream): in local mode only checks named in projects.required_checks are waited for; name the
        pending check so the key is what decides."""
        self.env.sql("UPDATE projects SET required_checks='unittest' WHERE id='zz-test-proj'")

    def test_must_merge_on_a_local_pass_while_github_checks_are_pending(self):
        self.require_unittest()
        self.ok("config", KEY, "1")
        seed_run(self.env, self.head)
        p = self.judge()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(len(self.merges()), 1)

    def test_must_not_merge_on_a_failed_local_run(self):
        self.ok("config", KEY, "1")
        seed_run(self.env, self.head, status="fail")
        self.refused("local gate run #1 fail")

    def test_must_not_merge_on_a_finished_failed_github_check(self):
        self.ok("config", KEY, "1")
        seed_run(self.env, self.head)
        self.env.seed_pr(checks=FINISHED_RED)
        self.refused("checks not green: unittest=FAILURE")

    def test_key_off_still_waits_for_github(self):
        self.require_unittest()
        seed_run(self.env, self.head)
        self.refused("checks not green")  # judge_ci_wait_s is 0: the pending check refuses as today

    def test_not_in_local_mode_the_key_changes_nothing(self):
        self.ok("config", KEY, "1")
        self.env.sql("UPDATE projects SET gate_cmd='' WHERE id='zz-test-proj'")
        self.refused("checks not green")
        self.assertEqual(runs(self.env), [])


@tch.own_tests_only
class FirstReviewOnTheLocalPass(tch.ReviewWaitsForGreen):
    def setUp(self):
        super().setUp()
        self.ok("config", tch.FLAG, "resume")
        e = self.env
        e.seed_project()
        e.sql("UPDATE projects SET gate_cmd='true' WHERE id='zz-test-proj'")
        e.sql("UPDATE goals SET project_id='zz-test-proj' WHERE id='G-001'")

    def gate_run(self, status):
        self.env.sql("INSERT INTO gate_runs(project_id,task_id,pr_url,kind,head_sha,status,cmd,created) "
                     "VALUES('zz-test-proj','T-0001',?,'pr',?,?,'true','t')", (PR_URL, tch.tra.SHA_A, status))

    def test_key_on_review_waits_for_the_local_run_then_starts_while_ci_is_pending(self):
        self.ok("config", KEY, "1")
        self.assertEqual(self.step(tch.tra.PENDING), [])
        queued = self.env.sql("SELECT status, head_sha FROM gate_runs")
        self.assertEqual([(r["status"], r["head_sha"]) for r in queued], [("queued", tch.tra.SHA_A)])  # no run: one queued
        self.assertEqual(self.step(tch.tra.PENDING), [])  # still queued: no second run, no review
        self.assertEqual(len(self.env.sql("SELECT id FROM gate_runs")), 1)
        self.env.sql("UPDATE gate_runs SET status='pass'")
        self.assertEqual(self.step(tch.tra.PENDING), [("reviewer", "reviewer-t-0001"), ("qa", "qa-t-0001")])

    def test_key_on_a_failed_run_starts_no_review(self):
        self.ok("config", KEY, "1")
        self.gate_run("fail")
        self.assertEqual(self.step(tch.tra.GREEN), [])

    def test_key_off_review_still_waits_for_green_ci(self):
        self.gate_run("pass")
        self.assertEqual(self.step(tch.tra.PENDING), [])
        self.assertEqual(len(self.step(tch.tra.GREEN)), 2)


class CoderRestartOnAFailedLocalRun(tcr.Base):
    def setUp(self):
        super().setUp()
        e = self.env
        e.seed_project()
        e.sql("UPDATE projects SET gate_cmd='true' WHERE id='zz-test-proj'")
        e.sql("UPDATE goals SET project_id='zz-test-proj' WHERE id='G-001'")
        self.tid = self.task()
        log = e.home / "gate-1.log"
        log.write_text("FAIL: test_a (test_mod.Case.test_a)\nERROR: test_b (test_other.Case.test_b)\n"
                       "FAIL: test_a (test_mod.Case.test_a)\n")
        e.sql("INSERT INTO gate_runs(project_id,task_id,pr_url,kind,head_sha,status,cmd,log_path,created) "
              "VALUES('zz-test-proj',?,?,'pr',?,'fail','true',?,'t')", (self.tid, tcr.pr_url(1), tcr.SHA, str(log)))

    def test_a_failed_run_restarts_the_coder_once_with_the_failing_tests(self):
        self.ok("config", KEY, "1")
        calls = self.tick({tcr.pr_url(1): (tcr.SHA, tcr.PENDING)})  # GitHub still running: the local run decides
        self.assertEqual(len(calls), 1)
        prompt = calls[0]["prompt"]
        self.assertIn("test_mod.Case.test_a, test_other.Case.test_b", prompt)
        self.assertIn("factory gate show 1", prompt)
        self.assertNotIn("gh run view", prompt)
        ev = json.loads(self.env.sql("SELECT detail FROM events WHERE action='coder-ci-resume'")[0][0])
        self.assertEqual((ev["source"], ev["gate_run"]), ("local-gate", 1))
        self.env.sql("UPDATE agents SET status='done' WHERE name='coder-t-0001'")
        self.assertEqual(self.tick({tcr.pr_url(1): (tcr.SHA, tcr.PENDING)}), [])  # once per head

    def test_key_off_the_failed_local_run_restarts_nothing_on_pending_ci(self):
        self.assertEqual(self.tick({tcr.pr_url(1): (tcr.SHA, tcr.PENDING)}), [])

    def test_a_passed_run_restarts_nothing_even_on_red_github_checks(self):
        self.ok("config", KEY, "1")
        self.env.sql("UPDATE gate_runs SET status='pass'")
        self.assertEqual(self.tick({tcr.pr_url(1): (tcr.SHA, tcr.RED)}), [])


@tch.own_tests_only
class PrcheckOnTheLocalRun(tp.PrcheckTests):
    def setUp(self):
        super().setUp()
        e = self.env
        e.sql("UPDATE projects SET gate_cmd='true' WHERE id='zz-test-proj'")
        e.sql("UPDATE tasks SET pr_url=? WHERE id='T-0001'", (PR_URL,))
        self.mark = e.home / "mark"
        self.stub_marker()  # commits: HEAD below is the head with the marker stub

    def test_key_on_a_pass_of_head_meets_check_5_without_running_affected(self):
        self.ok("config", KEY, "1")
        seed_run(self.env, self.head())
        p = self.prcheck(0, env={"AFF_MARK": str(self.mark)})
        self.assertIn("PASS affected: not run here: the local gate is the test run", p.stdout)
        self.assertFalse(self.mark.exists(), "ci/affected.py must not be started")

    def test_key_on_no_run_queues_one_and_fails_with_the_message(self):
        self.ok("config", KEY, "1")
        p = self.prcheck(1, env={"AFF_MARK": str(self.mark)})
        self.assertIn("local gate run queued; run factory done when it has passed", p.stdout)
        self.assertFalse(self.mark.exists())
        self.assertEqual([(r["status"], r["head_sha"]) for r in runs(self.env)], [("queued", self.head())])

    def test_key_off_check_5_runs_affected_as_today(self):
        p = self.prcheck(0, env={"AFF_MARK": str(self.mark)})
        self.assertIn("PASS affected:", p.stdout)
        self.assertEqual(self.mark.read_text().splitlines()[0], "ran")


if __name__ == "__main__":
    unittest.main()
