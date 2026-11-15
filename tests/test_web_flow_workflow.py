"""HM-50 (HM-68, HM-70): the flow JSON per workflow. A goal that is a story run in the engine's workflow.db gets that
workflow's diagram (simple, medium, huge; finish by CI mode), its children and its incidents; any other goal keeps the
old diagram. workflow.db is only ever read."""
import os
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_web_detail import A_INS, E_INS, T_INS  # noqa: E402
from test_web_flow_api import FlowCase  # noqa: E402
from test_web_queries import ts  # noqa: E402
from web import flow, flowdefs as fd  # noqa: E402

# the engine's own schema, read from its source so the test cannot drift from it
SCHEMA = re.search(r"(CREATE TABLE runs\(.*?)`", (ROOT / "go/internal/workflow/state.go").read_text(), re.S).group(1)
N = fd.N


class WorkflowCase(FlowCase):
    def seed_run(self, workflow="huge", ci="none", version=fd.WORKFLOW_DB_VERSION, incidents=()):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-90','p1','Story run','intent','1. a','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-90", "G-90", None, "Story HM-1", "s", "a", "coder", "in_progress", "coder-t-90", None, 1, ts(8, 0), ts(9, 0)))
        x(A_INS, ("coder-t-90", "coder", "G-90", None, "T-90", "live", "m", ts(8, 5), None))
        x(A_INS, ("review-hm-2-r1", "reviewer", "G-90", None, "T-90", "done", "m", ts(8, 30), ts(8, 40)))
        x(E_INS, (ts(8, 0), "engine", "workflow", "G-90", "workflow-chosen", workflow))
        self.con.commit()
        path = fd.db_path(self.con)
        w = sqlite3.connect(path)
        w.executescript(SCHEMA)
        w.execute(f"PRAGMA user_version={version}")
        w.execute("INSERT INTO runs(goal_id,story_key,workflow,task_id,state,created,updated,ci) "
                  "VALUES('G-90','HM-1',?,'T-90','building',?,?,?)", (workflow, ts(8, 0), ts(9, 0), ci))
        w.execute("INSERT INTO run_stories VALUES('G-90','HM-1',1)")
        for key, pos, state, rounds in (("HM-2", 1, "reviewed", 1), ("HM-3", 2, "fixing", 2)):
            w.execute("INSERT INTO children(goal_id,story_key,child_key,position,state,rounds,updated) VALUES('G-90','HM-1',?,?,?,?,?)",
                      (key, pos, state, rounds, ts(9, 0)))
        for child, kind, cause, summary, at in incidents:
            w.execute("INSERT INTO incidents(goal_id,child_key,kind,cause,actor,summary,detail,created) "
                      "VALUES('G-90',?,?,?,'engine',?,'',?)", (child, kind, cause, summary, at))
        w.commit()
        w.close()
        return path

    def ids(self, d):
        return [n["id"] for n in d["nodes"]]


class TestOldWorkflow(WorkflowCase):
    def test_a_goal_without_workflow_db_keeps_the_old_diagram_and_creates_no_file(self):
        self.seed()
        path = fd.db_path(self.con)
        d = self.build(flow.Scope.GOAL, "G-80")
        self.assertEqual(self.ids(d), [n for n, _ in flow.NODES])
        self.assertEqual([e["id"] for e in d["edges"]], [e[0] for e in flow.EDGES])
        self.assertEqual(d["workflow"]["kind"], fd.Kind.OLD)
        self.assertEqual((d["children"], d["layout"]), ([], None))
        self.assertFalse(os.path.exists(path))

    def test_a_goal_that_is_not_a_run_is_old(self):
        self.seed()
        self.seed_run()
        self.assertEqual(self.build(flow.Scope.GOAL, "G-80")["workflow"]["kind"], fd.Kind.OLD)

    def test_an_unknown_workflow_db_version_is_old_with_the_reason(self):
        self.seed_run(version=9)
        w = self.build(flow.Scope.GOAL, "G-90")["workflow"]
        self.assertEqual(w["kind"], fd.Kind.OLD)
        self.assertIn("user_version 9", w["note"])


class TestEngineDiagrams(WorkflowCase):
    def test_huge_with_ci_none(self):
        self.seed_run("huge", "none")
        d = self.build(flow.Scope.GOAL, "G-90")
        self.assertEqual(self.ids(d), [N.BOSS, N.ENGINE, N.ARCHITECT, N.BUILDER, N.CHILD_REVIEW, N.BRANCH_QA, N.MERGE_QUEUE,
                                       N.LAND, N.DONE, N.WAIT])
        nodes = self.by_id(d["nodes"])
        self.assertEqual({n for n, x in nodes.items() if x["planned"]}, {N.ARCHITECT, N.BRANCH_QA, N.MERGE_QUEUE})
        self.assertTrue(all(nodes[n]["agents"] == [] for n in (N.ARCHITECT, N.BRANCH_QA, N.MERGE_QUEUE)))
        for gone in ("lead", "pm", "judge", "coders", "director"):
            self.assertNotIn(gone, nodes)
        self.assertEqual(nodes[N.LAND]["note"], fd.NOTE_NO_TESTS)
        self.assertEqual(d["workflow"], {"kind": "huge", "origin": "chosen", "ci": "none", "ci_text": fd.CI_TEXT["none"],
                                         "state": "building", "story": "HM-1", "note": None})
        planned_edges = {e["id"] for e in d["edges"] if e["planned"]}
        self.assertIn(fd.E.NON_CONVERGENCE, planned_edges)
        self.assertTrue(all(e["pending"] for e in d["edges"] if e["planned"]))

    def test_the_agents_feed_builder_and_child_reviewer(self):
        self.seed_run("simple", "local")
        nodes = self.by_id(self.build(flow.Scope.GOAL, "G-90")["nodes"])
        self.assertEqual([a["name"] for a in nodes[N.BUILDER]["agents"]], ["coder-t-90"])
        self.assertEqual(nodes[N.BUILDER]["state"], flow.State.LIVE)
        self.assertEqual([a["name"] for a in nodes[N.CHILD_REVIEW]["agents"]], ["review-hm-2-r1"])
        self.assertEqual(nodes[N.CHILD_REVIEW]["state"], flow.State.FAIL)   # HM-3 is back with the builder
        self.assertEqual(nodes[N.CHILD_REVIEW]["note"], "1 of 2 reviewed, 3 fix rounds")
        self.assertEqual(nodes[N.ENGINE]["state"], flow.State.LIVE)
        self.assertEqual(nodes[N.ENGINE]["note"], "run building")

    def test_ci_github_ends_with_pull_request_gate_judge_merged(self):
        self.seed_run("simple", "github")
        d = self.build(flow.Scope.GOAL, "G-90")
        self.assertEqual(self.ids(d)[-7:], [N.PR, N.REVIEWER, N.QA, N.JUDGE, N.MAIN, N.DONE, N.WAIT])
        self.assertEqual(d["groups"], [{"id": N.GATE, "label": "Review gate", "nodes": [N.REVIEWER, N.QA]}])
        self.assertNotIn(N.ARCHITECT, self.ids(d))

    def test_ci_local_ends_with_affected_tests_and_land(self):
        self.seed_run("medium", "local")
        d = self.build(flow.Scope.GOAL, "G-90")
        self.assertEqual(self.ids(d)[-4:], [N.TESTS, N.LAND, N.DONE, N.WAIT])
        self.assertIn(N.ARCHITECT, self.ids(d))
        self.assertNotIn(N.BRANCH_QA, self.ids(d))

    def test_children_are_listed_with_state_and_rounds(self):
        self.seed_run()
        self.assertEqual(self.build(flow.Scope.GOAL, "G-90")["children"],
                         [{"key": "HM-2", "story": "HM-1", "state": "reviewed", "rounds": 1},
                          {"key": "HM-3", "story": "HM-1", "state": "fixing", "rounds": 2}])

    def test_the_task_page_draws_the_same_workflow_as_the_goal(self):
        self.seed_run("medium", "github")
        g, t = self.build(flow.Scope.GOAL, "G-90"), self.build(flow.Scope.TASK, "T-90")
        for key in ("workflow", "children", "layout"):
            self.assertEqual(t[key], g[key], key)
        self.assertEqual(self.ids(t), self.ids(g))

    def test_every_drawn_box_and_arrow_has_a_place(self):
        for (kind, ci), defn in fd.ENGINE_DEFS.items():
            with self.subTest(kind=kind, ci=ci):
                geo = fd.GEOMETRY[(kind, ci)]
                self.assertEqual(set(geo["boxes"]), {n[0] for n in defn.nodes})
                self.assertEqual(set(geo["edges"]), {e[0] for e in defn.edges})
                places = [(b["x"], b["y"]) for b in geo["boxes"].values()]
                self.assertEqual(len(places), len(set(places)), "two boxes on one place")

    def test_workflow_db_is_never_written(self):
        path = self.seed_run(incidents=((None, "warning", "land-refused", "checkout dirty", ts(9, 0)),))
        before = (os.path.getsize(path), os.path.getmtime(path), sorted(os.listdir(os.path.dirname(path))))
        self.build(flow.Scope.GOAL, "G-90")
        self.build(flow.Scope.TASK, "T-90")
        self.assertEqual((os.path.getsize(path), os.path.getmtime(path), sorted(os.listdir(os.path.dirname(path)))), before)


class TestIncidents(WorkflowCase):
    def test_incidents_are_timeline_marks_with_their_reason(self):
        self.seed_run("simple", "local", incidents=(
            ("HM-3", "rejection", "local-tests-failed", "2 tests failed: test_a, test_b", ts(9, 10)),
            (None, "warning", "land-refused", "the checkout has uncommitted changes", ts(9, 20))))
        d = self.build(flow.Scope.GOAL, "G-90")
        marks = [e for e in d["events"] if "incident" in e]
        self.assertEqual([(e["lane"], e["severity"], e["incident"]["cause"], e["incident"]["summary"]) for e in marks],
                         [(N.CHILD_REVIEW, flow.Severity.BAD, "local-tests-failed", "2 tests failed: test_a, test_b"),
                          (N.ENGINE, flow.Severity.WARN, "land-refused", "the checkout has uncommitted changes")])
        self.assertEqual([e["ref"]["table"] for e in marks], [flow.Table.INCIDENTS] * 2)
        self.assertEqual(self.by_id(d["nodes"])[N.TESTS]["state"], flow.State.FAIL)

    def test_the_old_workflow_has_no_incident_marks(self):
        self.seed()
        self.assertFalse(any("incident" in e for e in self.build(flow.Scope.GOAL, "G-80")["events"]))


if __name__ == "__main__":
    unittest.main()
