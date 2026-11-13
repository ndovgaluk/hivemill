"""DVDG-560: findings and Sequence phases of the flow debugger (web/flow_findings.py)."""
import datetime as dt
import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_web_detail as wd  # noqa: E402
from test_web_detail import A_INS, E_INS, M_INS, T_INS, V_INS  # noqa: E402
from test_web_queries import ts  # noqa: E402
from web import flow, flow_findings as ff  # noqa: E402

NOW = dt.datetime(2026, 10, 24, 12, 0).astimezone()
GOAL = "G-95"


class FindingsCase(wd.DetailCase):
    def setUp(self):
        super().setUp()
        self.con.execute("INSERT INTO goals VALUES(?,'p1','Findings goal','i','1. a','active',2,'owner',NULL,?,?)",
                         (GOAL, ts(8, 0), ts(8, 0)))

    def task(self, tid, created=(9, 0), status="in_progress"):
        self.con.execute(T_INS, (tid, GOAL, None, f"task {tid}", "s", "a", "coder", status, None, None, 1, ts(*created), ts(*created)))

    def agent(self, name, role, tid, start, end=(11, 50), status="done"):
        self.con.execute(A_INS, (name, role, GOAL, None, tid, status, "m", ts(*start) if start else None, ts(*end) if end else None))

    def build(self, scope=flow.Scope.GOAL, oid=GOAL):
        self.con.commit()
        self.con.row_factory = sqlite3.Row
        return flow.build(self.con, scope, oid, NOW)

    def kinds(self, d):
        return {f["kind"]: f for f in ff.findings(d)}


class TestDetectors(FindingsCase):
    def test_longest_wait_reported_above_threshold(self):
        self.task("T-951")
        self.agent("coder-1", "coder", "T-951", (11, 0))
        f = self.kinds(self.build())[ff.Kind.LONG_WAIT]
        self.assertEqual(f["severity"], flow.Severity.BAD)
        self.assertEqual(f["target"], {"kind": flow.FindingTarget.EDGE, "id": flow.Edge.PC})
        self.assertIn("T-951 waited 2h 00m before coding", f["text"])

    def test_short_wait_not_reported(self):
        self.task("T-951")
        self.agent("coder-1", "coder", "T-951", (9, 2))
        self.assertNotIn(ff.Kind.LONG_WAIT, self.kinds(self.build()))

    def test_rejections_reported_with_open_count(self):
        self.task("T-951")
        self.task("T-952")
        x = self.con.execute
        x(V_INS, ("T-951", "u", "a1", "reviewer", "fail", "s", "reviewer-1", ts(10, 0)))
        x(V_INS, ("T-952", "u", "b1", "qa", "fail", "s", "qa-2", ts(10, 10)))
        x(V_INS, ("T-951", "u", "a2", "reviewer", "pass", "s", "reviewer-1", ts(10, 30)))
        # HM-17: one finding per role that rejected, on that role's box
        got = {f["node"]: f for f in ff.findings(self.build()) if f["kind"] == ff.Kind.REJECTIONS}
        self.assertEqual(set(got), {flow.Node.REVIEWER, flow.Node.QA})
        qa, rev = got[flow.Node.QA], got[flow.Node.REVIEWER]
        self.assertEqual(qa["text"], "1 rejection by QA, 1 still open (T-952)")
        self.assertEqual(qa["severity"], flow.Severity.BAD)
        self.assertEqual(rev["text"], "1 rejection by Reviewer, all resolved")
        self.assertEqual(rev["severity"], flow.Severity.WARN)
        for f in (qa, rev):
            self.assertEqual(f["target"], {"kind": flow.FindingTarget.EDGE, "id": flow.Edge.RW})

    def test_no_rejection_no_finding(self):
        self.task("T-951")
        self.con.execute(V_INS, ("T-951", "u", "a1", "reviewer", "pass", "s", "reviewer-1", ts(10, 0)))
        self.assertNotIn(ff.Kind.REJECTIONS, self.kinds(self.build()))

    def seed_review(self, reviewer_start):
        self.task("T-951", status="in_review")
        self.agent("coder-1", "coder", "T-951", (9, 5), (9, 55))
        self.con.execute(E_INS, (ts(10, 0), "coder-1", "task", "T-951", "update", "status=in_review pr=u"))
        self.agent("reviewer-1", "reviewer", "T-951", reviewer_start)

    def test_unstaffed_review_reported(self):
        self.seed_review((10, 5))
        self.agent("lead-95", "lead", None, (8, 30), None, "live")
        self.con.execute(M_INS, ("director", "lead-95", "request", "PR green, nobody reviewing", None, GOAL, None, ts(10, 3)))
        d = self.build()
        f = self.kinds(d)[ff.Kind.UNSTAFFED_REVIEW]
        nudge = next(e for e in d["events"] if e["title"].endswith("PR green, nobody reviewing"))
        self.assertEqual(f["severity"], flow.Severity.WARN)
        self.assertEqual(f["target"], {"kind": flow.FindingTarget.EVENT, "id": nudge["id"]})
        self.assertIn("5m 00s", f["text"])

    def test_review_started_promptly_not_reported(self):
        self.seed_review((10, 0, 30))
        self.assertNotIn(ff.Kind.UNSTAFFED_REVIEW, self.kinds(self.build()))

    def test_missing_start_event_reported(self):
        self.task("T-951", status="in_review")
        self.agent("coder-1", "coder", "T-951", None, None)
        f = self.kinds(self.build())[ff.Kind.MISSING_START]
        self.assertEqual(f["target"], {"kind": flow.FindingTarget.NODE, "id": flow.Node.CODERS})
        self.assertNotIn(ff.Kind.LONG_WAIT, self.kinds(self.build()))   # an unknown wait is never "slow"

    def test_stage_with_start_not_reported(self):
        self.task("T-951", status="in_review")
        self.agent("coder-1", "coder", "T-951", (9, 3))
        self.assertNotIn(ff.Kind.MISSING_START, self.kinds(self.build()))

    def with_costs(self, d, total, unattributed=None, overhead=None):
        d["totals"].update(cost=total, unattributed_cost=unattributed, overhead_cost=overhead)
        return d

    def test_unattributed_cost_reported_above_share(self):
        self.task("T-951")
        f = self.kinds(self.with_costs(self.build(), 4.0, 1.5))[ff.Kind.UNATTRIBUTED]
        self.assertEqual(f["text"], "$1.50 of $4.00 is not attributed to any agent")

    def test_small_unattributed_not_reported(self):
        self.task("T-951")
        self.assertNotIn(ff.Kind.UNATTRIBUTED, self.kinds(self.with_costs(self.build(), 4.0, 0.2)))
        self.assertNotIn(ff.Kind.UNATTRIBUTED, self.kinds(self.with_costs(self.build(), None, 1.5)))   # unknown total
        self.assertNotIn(ff.Kind.UNATTRIBUTED, self.kinds(self.with_costs(self.build(), 4.0, None)))

    def test_goal_overhead_reported_above_share(self):
        self.task("T-951")
        f = self.kinds(self.with_costs(self.build(), 21.39, overhead=8.11))[ff.Kind.OVERHEAD]
        self.assertEqual(f["text"], "$8.11 of $21.39 is goal overhead (HQ and lead)")
        task = self.with_costs(self.build(flow.Scope.TASK, "T-951"), 21.39, overhead=8.11)
        self.assertNotIn(ff.Kind.OVERHEAD, self.kinds(task))

    def test_findings_sorted_bad_first_then_by_size(self):
        self.task("T-951")
        self.task("T-952")
        self.agent("coder-1", "coder", "T-951", (11, 0))
        x = self.con.execute
        for i, (tid, role) in enumerate((("T-951", "reviewer"), ("T-952", "qa"), ("T-952", "reviewer"))):
            x(V_INS, (tid, "u", f"s{i}", role, "fail", "s", f"{role}-x", ts(10, i)))
        d = self.with_costs(self.build(), 10.0, 9.0, 5.0)
        got = ff.findings(d)
        ranks = [ff.SEV_RANK[f["severity"]] for f in got]
        self.assertEqual(ranks, sorted(ranks))
        bad = [f["kind"] for f in got if f["severity"] == flow.Severity.BAD]
        # reviewer (2) and QA (1) rejections, one finding each (HM-17), both outrank a 2h wait share
        self.assertEqual(bad, [ff.Kind.REJECTIONS, ff.Kind.REJECTIONS, ff.Kind.LONG_WAIT])
        warn = [f["kind"] for f in got if f["severity"] == flow.Severity.WARN]
        self.assertEqual(warn, [ff.Kind.UNATTRIBUTED, ff.Kind.OVERHEAD])   # 90% before 50%
        self.assertTrue(all(ff.SIZE not in f for f in got))


class TestPhases(FindingsCase):
    def seed_goal(self):
        wd.TestFlow.seed_flow(self, merged=True)
        wd.TestFlow.seed_hq_chain(self)

    def test_phases_cover_every_event_once(self):
        self.seed_goal()
        for scope, oid in ((flow.Scope.GOAL, "G-80"), (flow.Scope.TASK, "T-80")):
            with self.subTest(scope):
                d = self.build(scope, oid)
                ph = ff.phases(d, self.con, NOW)
                ids = [i for p in ph for i in p["event_ids"]]
                self.assertEqual(sorted(ids), sorted(e["id"] for e in d["events"]))
                self.assertEqual(len(ids), len(set(ids)))
                firsts = [min(t for t in (next(e for e in d["events"] if e["id"] == i)["t_s"] for i in p["event_ids"]) if t is not None)
                          for p in ph]
                self.assertEqual(firsts, sorted(firsts))
                self.assertTrue(all(p["title"] and p["summary"] for p in ph))

    def test_phases_goal_and_task_grouping(self):
        self.seed_goal()
        d = self.build(flow.Scope.GOAL, "G-80")
        ph = ff.phases(d, self.con, NOW)
        self.assertEqual(ph[0]["title"], ff.PhaseTitle.SETUP)
        setup = {next(e for e in d["events"] if e["id"] == i)["title"] for i in ph[0]["event_ids"]}
        self.assertIn("request: new goal G-80", setup)
        self.assertTrue(ph[1]["title"].startswith("T-80"))
        self.con.execute(M_INS, ("coder-80b", "lead-g-80-a", "report", "fixing the findings", None, "G-80", "T-80", ts(10, 10)))
        t = self.build(flow.Scope.TASK, "T-80")
        titles = [p["title"] for p in ff.phases(t, self.con, NOW)]
        self.assertEqual(titles, [ff.PhaseTitle.SPEC, ff.PhaseTitle.CODING.format(n=1), ff.PhaseTitle.REVIEW.format(n=1),
                                  ff.PhaseTitle.CODING.format(n=2), ff.PhaseTitle.REVIEW.format(n=2), ff.PhaseTitle.MERGE])

    def test_payload_has_findings_and_phases(self):
        self.seed_goal()
        self.con.commit()
        for path in ("/api/flow/goal/G-80.json", "/api/flow/task/T-80.json"):
            with self.subTest(path):
                d = json.loads(self.get(path)[2])
                self.assertTrue(d["phases"])
                self.assertIsInstance(d["findings"], list)
                ids = [i for p in d["phases"] for i in p["event_ids"]]
                self.assertEqual(sorted(ids), sorted(e["id"] for e in d["events"]))
        d = json.loads(self.get("/api/flow/goal/G-80.json")[2])
        self.assertIn(ff.Kind.REJECTIONS, {f["kind"] for f in d["findings"]})


if __name__ == "__main__":
    unittest.main()
