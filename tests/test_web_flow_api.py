"""DVDG-553: the flow debugger's JSON (web/flow.py) through the real server routes /api/flow/{goal,task}/<id>.json."""
import datetime as dt
import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_web_detail as wd  # noqa: E402
from harness import FactoryTestCase  # noqa: E402
from test_web_detail import A_INS, E_INS, T_INS  # noqa: E402
from test_web_queries import ts  # noqa: E402
from web import flow, server  # noqa: E402

CONTRACT_KEYS = {"scope", "id", "title", "status", "start", "now", "elapsed_s", "show_text", "totals", "nodes", "edges", "lanes",
                 "events", "findings", "phases"}
EVENT_KEYS = {"id", "key", "ref", "task_id", "goal_id", "t_s", "ts", "lane", "row", "edge", "dir", "from", "to", "from_node",
              "to_node", "kind", "severity", "title", "is_instruction", "body_html", "tokens", "cost", "cost_note", "cost_exact"}
SECRETS = ("BODY-SECRET", "FIX-BODY", "SUMMARY-SECRET", "SPEC-SECRET", "ACC-SECRET")
TEXT_COLUMNS = re.compile(r"\b(body|summary|spec|acceptance)\b")
NOW = dt.datetime(2026, 10, 24, 12, 0).astimezone()
WAIT_PR = "https://github.com/example/repo/pull/7"
NON_LOOPBACK = "203.0.113.5"   # documentation range: never bound, only set on the app the handler reads


class FlowCase(wd.DetailCase):
    def json(self, path, code=200):
        status, headers, body = self.get(path)
        self.assertEqual(status, code, path)
        self.assertEqual(headers["Content-Type"], flow_json_type())
        return json.loads(body)

    def seed(self):
        """The DVDG-544 flow seed (reviewer FAIL, coder restart, PASS) plus a reviewer session that starts after the PR."""
        wd.TestFlow.seed_flow(self)        # the DVDG-544 seed, reused without importing (and re-running) its tests
        wd.TestFlow.seed_hq_chain(self)
        self.con.execute(A_INS, ("reviewer-80", "reviewer", "G-80", "g-80-a", "T-80", "done", "m", ts(9, 45), ts(9, 50)))
        self.con.commit()

    def build(self, scope, oid, show_text=False):
        self.con.row_factory = sqlite3.Row
        return flow.build(self.con, scope, oid, NOW, show_text)

    @staticmethod
    def by_id(items, key="id"):
        return {i[key]: i for i in items}

    def agents(self, node):
        return self.by_id(node["agents"], "name")


def flow_json_type():
    return server.JSON_TYPE


class TestRoutes(FlowCase):
    def test_goal_and_task_routes_return_the_contract(self):
        self.seed()
        for scope, oid in ((flow.Scope.GOAL, "G-80"), (flow.Scope.TASK, "T-80")):
            with self.subTest(scope):
                d = self.json(f"/api/flow/{scope}/{oid}.json")
                self.assertEqual(set(d) - {"goal_id"}, CONTRACT_KEYS)
                self.assertEqual((d["scope"], d["id"]), (scope, oid))
                self.assertEqual([n["id"] for n in d["nodes"]], [n for n, _ in flow.NODES])
                self.assertEqual([e["id"] for e in d["edges"]], [e[0] for e in flow.EDGES])
                self.assertTrue(d["events"])
                for ev in d["events"]:
                    self.assertEqual(set(ev), EVENT_KEYS)

    def test_unknown_id_is_404_json(self):
        for path in ("/api/flow/goal/G-404.json", "/api/flow/task/T-404.json"):
            with self.subTest(path):
                self.assertEqual(self.json(path, 404)["error"], "not found")

    def test_bad_scope_or_id_is_not_routed(self):
        for path in ("/api/flow/plan/G-80.json", "/api/flow/goal/g80.json"):
            with self.subTest(path):
                self.assertEqual(self.get(path)[0], 404)


class TestWaitsAndRework(FlowCase):
    def test_wait_edges_come_from_real_timestamps(self):
        self.seed()
        edges = self.by_id(self.build(flow.Scope.TASK, "T-80")["edges"])
        self.assertEqual(edges[flow.Edge.PC]["wait_s"], 10 * 60)    # created 09:00 → coder-80 started 09:10
        self.assertEqual(edges[flow.Edge.CG]["wait_s"], 5 * 60)     # in_review 09:40 → reviewer-80 started 09:45

    def test_open_waits_count_until_now(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-81','p1','Open','i','1. a','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(8, 0)))
        x(T_INS, ("T-81", "G-81", None, "queued", "s", "a", "coder", "todo", None, None, 0, ts(11, 0), ts(11, 0)))
        x(T_INS, ("T-82", "G-81", None, "unreviewed", "s", "a", "coder", "in_review", "coder-82", "u", 1, ts(9, 0), ts(9, 0)))
        x(A_INS, ("coder-82", "coder", "G-81", None, "T-82", "done", "m", ts(9, 5), ts(11, 20)))
        x(E_INS, (ts(11, 30), "coder-82", "task", "T-82", "update", "status=in_review pr=u"))
        self.con.commit()
        edges = self.by_id(self.build(flow.Scope.TASK, "T-81")["edges"])
        self.assertEqual(edges[flow.Edge.PC]["wait_s"], 60 * 60)         # still queued: 11:00 → now 12:00
        edges = self.by_id(self.build(flow.Scope.TASK, "T-82")["edges"])
        self.assertEqual(edges[flow.Edge.CG]["wait_s"], 30 * 60)         # PR at 11:30, no reviewer yet: until now
        self.assertEqual(edges[flow.Edge.CG]["severity"], flow.Severity.WARN)

    def test_waiting_box_is_live_when_no_agent_runs_and_says_what_for(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-81','p1','Open','i','1. a','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(8, 0)))
        x(T_INS, ("T-81", "G-81", None, "queued", "s", "a", "coder", "todo", None, None, 0, ts(11, 0), ts(11, 0)))
        x(T_INS, ("T-82", "G-81", None, "unreviewed", "s", "a", "coder", "in_review", "coder-82", "u", 1, ts(9, 0), ts(9, 0)))
        x(A_INS, ("coder-82", "coder", "G-81", None, "T-82", "done", "m", ts(9, 5), ts(11, 20)))
        x(E_INS, (ts(11, 30), "coder-82", "task", "T-82", "update", "status=in_review pr=u"))
        self.con.commit()
        x("UPDATE tasks SET pr_url=? WHERE id='T-82'", (WAIT_PR,))
        self.con.commit()
        wait = self.by_id(self.build(flow.Scope.GOAL, "G-81")["nodes"])[flow.Node.WAIT]
        self.assertEqual(wait["state"], flow.State.LIVE)
        self.assertEqual(wait["links"], [{"label": f"{flow.WAIT_LINK_LABEL} T-82", "url": WAIT_PR}])
        self.assertEqual(wait["current_s"], 40 * 60)                    # the last session ended 11:20, now 12:00
        self.assertEqual(wait["work_s"], 40 * 60)                       # every wait so far: there was only this one
        self.assertEqual(wait["note"], f"{flow.WAIT_REVIEW}: T-82")     # an open PR outranks the queued task
        self.assertEqual(wait["agents"], [])
        x("UPDATE tasks SET status='in_progress' WHERE id='T-82'")
        x("DELETE FROM events WHERE entity_id='T-82'")
        self.con.commit()
        wait = self.by_id(self.build(flow.Scope.GOAL, "G-81")["nodes"])[flow.Node.WAIT]
        self.assertEqual(wait["note"], f"{flow.WAIT_QUEUE}: T-81")
        self.assertEqual(wait["links"], [])
        x("UPDATE agents SET status='live', ended=NULL WHERE name='coder-82'")   # somebody runs: not waiting
        self.con.commit()
        wait = self.by_id(self.build(flow.Scope.GOAL, "G-81")["nodes"])[flow.Node.WAIT]
        self.assertEqual((wait["state"], wait["current_s"], wait["note"]), (flow.State.IDLE, None, None))
        self.assertEqual(wait["work_s"], 0)                             # the coder has run since 09:05 without a gap
        x(A_INS, ("qa-82", "qa", "G-81", None, "T-82", "done", "m", ts(9, 0), ts(9, 1)))   # 09:01 to 09:05 nobody ran
        self.con.commit()
        wait = self.by_id(self.build(flow.Scope.GOAL, "G-81")["nodes"])[flow.Node.WAIT]
        self.assertEqual(wait["work_s"], 4 * 60)
        x("DELETE FROM agents WHERE name='qa-82'")
        x("UPDATE agents SET status='done', ended=? WHERE name='coder-82'", (ts(11, 20),))
        x("UPDATE goals SET status='done' WHERE id='G-81'")                       # a closed goal waits for nothing
        self.con.commit()
        wait = self.by_id(self.build(flow.Scope.GOAL, "G-81")["nodes"])[flow.Node.WAIT]
        self.assertEqual(wait["state"], flow.State.IDLE)

    def test_reviewer_fail_then_restart_is_one_rework_instruction(self):
        self.seed()
        d = self.build(flow.Scope.TASK, "T-80")
        rw = self.by_id(d["edges"])[flow.Edge.RW]
        self.assertEqual(rw["counts"], {"forward": 1, "back": 0})
        self.assertEqual(rw["severity"], flow.Severity.BAD)
        fail = [e for e in d["events"] if e["edge"] == flow.Edge.RW]
        self.assertEqual(len(fail), 1)
        self.assertTrue(fail[0]["is_instruction"])
        self.assertEqual(fail[0]["from_node"], flow.Node.GATE)
        self.assertEqual(fail[0]["to_node"], flow.Node.CODERS)
        self.assertEqual(d["totals"]["rejections"], 1)

    def test_missing_start_is_unknown_not_zero(self):
        self.seed()
        self.con.execute(A_INS, ("coder-80c", "coder", "G-80", "g-80-a", "T-80", "done", "m", None, None))
        self.con.commit()
        nodes = self.by_id(self.build(flow.Scope.TASK, "T-80")["nodes"])
        self.assertIsNone(nodes[flow.Node.CODERS]["work_s"])
        self.assertIsNone(self.agents(nodes[flow.Node.CODERS])["coder-80c"]["work_s"])
        self.assertEqual(self.agents(nodes[flow.Node.CODERS])["coder-80"]["work_s"], 30 * 60)

    def test_every_session_counts_from_spawn_and_end_events(self):
        self.seed()
        x = self.con.execute
        x(E_INS, (ts(9, 10), "lead-g-80-a", "agent", "coder-80", "spawn", "{}"))
        x(E_INS, (ts(9, 20), "coder-80", "agent", "coder-80", "done", "first"))
        x(E_INS, (ts(9, 30), "lead-g-80-a", "agent", "coder-80", "spawn", "{}"))
        x(E_INS, (ts(9, 40), "coder-80", "agent", "coder-80", "reaped", None))
        self.con.commit()
        d = self.build(flow.Scope.TASK, "T-80")
        coders = self.by_id(d["nodes"])[flow.Node.CODERS]
        self.assertEqual(self.agents(coders)["coder-80"]["work_s"], 20 * 60)
        row = next(r for lane in d["lanes"] for r in lane["rows"] if r["name"] == "coder-80")
        self.assertEqual([s["kind"] for s in row["spans"]], [flow.SpanKind.WAIT, flow.SpanKind.WORK, flow.SpanKind.WORK])

    def test_reviewer_span_with_a_fail_verdict_is_a_fail_span(self):
        self.seed()
        d = self.build(flow.Scope.GOAL, "G-80")
        row = next(r for lane in d["lanes"] for r in lane["rows"] if r["name"] == "reviewer-80")
        self.assertEqual([s["kind"] for s in row["spans"]], [flow.SpanKind.FAIL])
        self.assertEqual(self.by_id(d["nodes"])[flow.Node.LEAD]["state"], flow.State.LIVE)


class TestKeys(FlowCase):
    def test_event_ids_are_stable_and_unique(self):
        self.seed()
        for scope, oid in ((flow.Scope.GOAL, "G-80"), (flow.Scope.TASK, "T-80")):
            with self.subTest(scope):
                a = [e["id"] for e in self.build(scope, oid)["events"]]
                self.assertEqual(a, [e["id"] for e in self.build(scope, oid)["events"]])
                self.assertEqual(len(a), len(set(a)))
                for e in self.build(scope, oid)["events"]:
                    self.assertEqual(e["id"], e["key"])

    def test_event_ref_points_at_the_source_row(self):
        self.seed()
        self.con.execute(E_INS, (ts(10, 50), "judge", "task", "T-80", flow.Action.MERGED, "@cafebabe"))
        self.con.commit()
        events = self.build(flow.Scope.TASK, "T-80")["events"]
        prefix = {flow.Table.MESSAGES: flow.Key.MESSAGE, flow.Table.VERDICTS: flow.Key.VERDICT, flow.Table.EVENTS: flow.Key.EVENT}
        cols = {flow.Table.MESSAGES: "created", flow.Table.VERDICTS: "created", flow.Table.EVENTS: "ts"}
        seen = set()
        for e in events:
            table, rowid = e["ref"]["table"], e["ref"]["rowid"]
            if table == flow.Table.TASKS:
                self.assertEqual(e["key"], f"{flow.Key.SPEC}T-80")
                self.assertEqual(self.con.execute("SELECT id FROM tasks WHERE rowid=?", (rowid,)).fetchone()[0], "T-80")
                continue
            self.assertEqual(e["key"], f"{prefix[table]}{rowid}")
            row = self.con.execute(f"SELECT {cols[table]} FROM {table} WHERE id=?", (rowid,)).fetchone()
            self.assertEqual(row[0], e["ts"])
            seen.add(table)
        self.assertEqual(seen, set(prefix))


class TestText(FlowCase):
    def test_text_off_never_selects_or_returns_bodies(self):
        self.seed()
        sql = []
        self.con.set_trace_callback(sql.append)
        self.addCleanup(self.con.set_trace_callback, None)
        for scope, oid in ((flow.Scope.GOAL, "G-80"), (flow.Scope.TASK, "T-80")):
            d = self.build(scope, oid)
            self.assertFalse(d["show_text"])
            self.assertTrue(all(e["body_html"] is None for e in d["events"]))
        self.assertTrue(sql)
        self.assertEqual([s for s in sql if TEXT_COLUMNS.search(s)], [])
        page = self.get("/api/flow/goal/G-80.json")[2].decode() + self.get("/api/flow/task/T-80.json")[2].decode()
        for secret in SECRETS:
            self.assertNotIn(secret, page)

    def test_text_on_loopback_returns_rendered_markdown(self):
        """Guard accept case: serve_show_text=1 on the loopback bind the test server uses."""
        self.seed()
        self.con.execute("INSERT INTO config(key,value) VALUES(?,'1')", ("serve_show_text",))
        self.con.commit()
        d = self.json("/api/flow/goal/G-80.json")
        self.assertTrue(d["show_text"])
        bodies = {e["key"]: e["body_html"] for e in d["events"] if e["body_html"]}
        html = " ".join(bodies.values())
        self.assertIn("FIX-BODY", html)
        self.assertIn("<strong>the flow</strong>", html)
        self.assertNotIn("<script>", html)              # md() escapes before it adds tags
        self.assertIn("SPEC-SECRET", html)              # the task's spec is the pm → coder instruction

    def test_text_on_non_loopback_bind_stays_hidden(self):
        """Guard reject case: the same setting on a LAN bind shows no text, through the real handler."""
        self.seed()
        self.con.execute("INSERT INTO config(key,value) VALUES(?,'1')", ("serve_show_text",))
        self.con.commit()
        self.httpd.app.bind = NON_LOOPBACK
        d = self.json("/api/flow/goal/G-80.json")
        self.assertFalse(d["show_text"])
        page = json.dumps(d)
        for secret in SECRETS:
            self.assertNotIn(secret, page)


class TestCliKey(FactoryTestCase):
    def test_message_key_matches_cli(self):
        e = self.env
        e.seed_goal()
        e.sql("UPDATE goals SET created=?", (ts(8, 0),))
        e.seed_agent("zz-test-director", "director")
        e.seed_agent("lead-g-001-a", "lead", goal="G-001", team="g-001-a")
        e.seed_team("g-001-a", "G-001", lead="lead-g-001-a")
        p = e.run("msg", "lead-g-001-a", "brief G-001", "plan it", "--goal", "G-001", agent="zz-test-director")
        self.assertEqual(p.returncode, 0, p.stderr)
        key = re.match(r"(M\d+) → ", p.stdout).group(1)
        con = e.db()
        try:
            d = flow.build(con, flow.Scope.GOAL, "G-001", NOW)
        finally:
            con.close()
        ev = next(x for x in d["events"] if x["kind"] == flow.EventKind.MSG and x["title"].endswith(": brief G-001"))
        self.assertEqual(ev["key"], key)
        self.assertEqual((ev["from_node"], ev["to_node"], ev["edge"]), (flow.Node.DIRECTOR, flow.Node.LEAD, flow.Edge.DL))


if __name__ == "__main__":
    unittest.main()
