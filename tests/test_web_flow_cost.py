"""DVDG-555: tokens and cost per box and per step (web/flowcost.py) from real session logs in a temp projects dir."""
import datetime as dt
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_web_detail import A_INS, M_INS, T_INS  # noqa: E402
from test_web_queries import ts  # noqa: E402
from test_web_server import ServerCase  # noqa: E402
from test_web_tokens import line, usage_row  # noqa: E402
from web import flow, flowcost, prices, tokens  # noqa: E402

NOW = dt.datetime(2026, 10, 24, 12, 0).astimezone()
SONNET, OPUS = "claude-sonnet-5-5", "claude-opus-5-5"
SID, CODER, TASK, GOAL = "s90", "coder-90", "T-90", "G-90"


def utc(h, m):
    """The log's form of a local time: UTC with Z, as Claude Code writes it."""
    return dt.datetime(2026, 10, 24, h, m).astimezone().astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def session_sum(tok):
    """session_tokens() counts input, output and cache writes (not cache reads)."""
    return tok["input"] + tok["output"] + tok["cache_write"]


class CostCase(ServerCase):
    def setUp(self):
        super().setUp()
        self.logs = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.logs, True)
        x = self.con.execute
        x("INSERT INTO goals VALUES(?,'p1','Cost goal','i','1. a','active',2,'owner',NULL,?,?)", (GOAL, ts(9, 0), ts(9, 0)))
        x(T_INS, (TASK, GOAL, None, "costed", "s", "a", "coder", "in_progress", CODER, None, 1, ts(9, 50), ts(9, 50)))
        x(A_INS, (CODER, "coder", GOAL, None, TASK, "done", "m", ts(9, 55), ts(10, 30)))
        x("UPDATE agents SET session_id=? WHERE name=?", (SID, CODER))
        x(M_INS, (CODER, "lead-90", "report", "first step", None, GOAL, TASK, ts(10, 6)))
        x(M_INS, (CODER, "lead-90", "report", "second step", None, GOAL, TASK, ts(10, 13)))
        self.con.commit()

    def log(self, sid, rows, project="p", sub=None):
        rel = f"{project}/{sid}.jsonl" if sub is None else f"{project}/{sid}/subagents/{sub}.jsonl"
        p = self.logs / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(line(r) for r in rows))
        return p

    def rows(self, *times, model=SONNET, inp=10, out=100, sid=SID):
        return [usage_row(sid, f"m{sid}{i}", f"r{sid}{i}", utc(h, m), inp, out, model=model) for i, (h, m) in enumerate(times)]

    def usage(self, cache=None):
        idx = tokens.TokenIndex(self.logs)
        idx.refresh()
        return flowcost.Usage(idx.snapshot(), idx, cache or flowcost.LineCache()), idx

    def build(self, scope=flow.Scope.TASK, oid=TASK, usage=None):
        self.con.row_factory = sqlite3.Row
        d = flow.build(self.con, scope, oid, NOW)
        return flowcost.fill(d, self.con, usage or self.usage()[0])

    @staticmethod
    def by_title(d):
        return {e["title"]: e for e in d["events"]}

    @staticmethod
    def agent(d, name):
        return next(a for n in d["nodes"] for a in n["agents"] if a["name"] == name)


class TestSplit(CostCase):
    def test_step_usage_splits_a_session_between_its_events(self):
        self.log(SID, self.rows((10, 0), (10, 5), (10, 12)))
        ev = self.by_title(self.build())
        self.assertEqual(ev["report: first step"]["tokens"]["output"], 200)    # 10:00 and 10:05
        self.assertEqual(ev["report: second step"]["tokens"]["output"], 100)   # 10:12
        self.assertTrue(ev["report: first step"]["cost_exact"])

    def test_usage_before_first_event_goes_to_first_event(self):
        self.log(SID, self.rows((9, 56), (10, 6)))
        ev = self.by_title(self.build())
        self.assertEqual(ev["report: first step"]["tokens"]["output"], 200)    # 09:56 and the request at 10:06 itself
        self.assertEqual(ev["report: second step"]["tokens"], {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
        self.assertEqual(ev["report: second step"]["cost"], 0.0)               # read in full: a real zero

    def test_tail_after_last_event_is_reported_as_open_remainder(self):
        self.log(SID, self.rows((10, 0), (10, 20), (10, 25)))
        d = self.build()
        ev = self.by_title(d)
        self.assertEqual(sum(e["tokens"]["output"] for e in ev.values() if e["from"] == CODER), 100)
        a = self.agent(d, CODER)
        self.assertEqual(a["after_last_event"]["tokens"]["output"], 200)
        self.assertEqual(a["tokens"]["output"], 300)                            # the node still counts the tail
        coders = next(n for n in d["nodes"] if n["id"] == flow.Node.CODERS)
        self.assertEqual(coders["tokens"]["output"], 300)

    def test_step_usage_sums_to_session_total(self):
        self.log(SID, self.rows((9, 58), (10, 3), (10, 12), (10, 40)))
        self.log(SID, self.rows((10, 10), sid="sub1"), sub="agent-1")        # a subagent log counts towards its session
        d = self.build()
        a = self.agent(d, CODER)
        steps = sum(session_sum(e["tokens"]) for e in d["events"] if e["from"] == CODER)
        self.assertEqual(steps + session_sum(a["after_last_event"]["tokens"]), tokens.session_tokens(SID, self.logs))
        cents = round(sum(e["cost"] for e in d["events"] if e["from"] == CODER) + a["after_last_event"]["cost"], 2)
        self.assertEqual(cents, round(a["cost"], 2))

    def test_two_events_inside_one_request_never_split_it(self):
        x = self.con.execute
        x(M_INS, (CODER, "lead-90", "report", "same minute", None, GOAL, TASK, ts(10, 6, 30)))
        self.con.commit()
        self.log(SID, self.rows((10, 6)))
        ev = self.by_title(self.build())
        got = [e["tokens"]["output"] for e in ev.values() if e["from"] == CODER]
        self.assertEqual(sorted(got), [0, 0, 100])


class TestUnknownAndTotals(CostCase):
    def test_unknown_session_gives_null_not_zero(self):
        x = self.con.execute
        x(T_INS, ("T-91", GOAL, None, "no log", "s", "a", "coder", "in_progress", "coder-91", None, 1, ts(9, 50), ts(9, 50)))
        x(A_INS, ("coder-91", "coder", GOAL, None, "T-91", "done", "m", ts(9, 55), ts(10, 30)))
        x(M_INS, ("coder-91", "lead-90", "report", "lost step", None, GOAL, "T-91", ts(10, 6)))
        self.con.commit()
        self.log(SID, self.rows((10, 0)))
        d = self.build(oid="T-91")
        ev = self.by_title(d)["report: lost step"]
        self.assertIsNone(ev["tokens"])
        self.assertIsNone(ev["cost"])
        self.assertFalse(ev["cost_exact"])
        self.assertIn("coder-91", ev["cost_note"])
        coders = next(n for n in d["nodes"] if n["id"] == flow.Node.CODERS)
        self.assertIsNone(coders["cost"])
        self.assertIn("coder-91", coders["cost_note"])

    def test_node_and_totals_match_task_usage(self):
        self.log(SID, self.rows((10, 0), (10, 12)))
        self.log("orphan", self.rows((10, 1), sid="orphan"), project=f"-home-user-factory-worktrees-{GOAL}-{TASK}")
        usage, idx = self.usage()
        d = self.build(usage=usage)
        self.con.row_factory = sqlite3.Row
        snap = idx.snapshot()
        tu = tokens.task_usage(snap, tokens.attribute(snap, self.con), self.con, TASK)
        rows = {r["agent"]: r for r in tu["rows"]}
        coders = next(n for n in d["nodes"] if n["id"] == flow.Node.CODERS)
        self.assertAlmostEqual(coders["cost"], rows[CODER]["cost"], places=6)
        self.assertAlmostEqual(d["totals"]["cost"], tu["totals"]["cost"], places=6)
        self.assertAlmostEqual(d["totals"]["unattributed_cost"], rows[flowcost.UNATTRIBUTED]["cost"], places=6)
        self.assertGreater(d["totals"]["unattributed_cost"], 0)

    def test_fast_mode_and_model_pricing_use_prices_cost(self):
        r = usage_row(SID, "mf", "rf", utc(10, 0), 1000, 2000, model=OPUS)
        r["message"]["usage"]["speed"] = flowcost.FAST
        self.log(SID, [r])
        ev = self.by_title(self.build())["report: first step"]
        want = prices.cost(OPUS, {"input": 1000, "output": 2000}, flowcost.FAST)
        self.assertAlmostEqual(ev["cost"], want, places=6)
        self.assertGreater(want, prices.cost(OPUS, {"input": 1000, "output": 2000}))

    def test_index_not_ready_says_so(self):
        self.con.row_factory = sqlite3.Row
        d = flowcost.fill(flow.build(self.con, flow.Scope.TASK, TASK, NOW), self.con, flowcost.Usage({"rows": []}))
        self.assertTrue(all(e["cost"] is None and e["cost_note"] == flowcost.Note.NO_INDEX for e in d["events"]))


class TestReadsAndRoute(CostCase):
    def test_refresh_of_unchanged_logs_reads_no_bytes(self):
        self.log(SID, self.rows((10, 0), (10, 12)))
        cache = flowcost.LineCache()
        usage, _ = self.usage(cache)
        self.build(usage=usage)
        first = cache.bytes_read
        self.assertGreater(first, 0)
        self.build(usage=usage)
        self.build(scope=flow.Scope.GOAL, oid=GOAL, usage=usage)
        self.assertEqual(cache.bytes_read, first)

    def test_large_log_is_bounded(self):
        self.log(SID, self.rows(*[(10, m) for m in range(0, 12)]))
        cap = 600
        cache = flowcost.LineCache()
        with mock.patch.object(flowcost, "MAX_READ_BYTES", cap):
            usage, _ = self.usage(cache)
            d = self.build(usage=usage)
        self.assertLessEqual(cache.bytes_read, cap)
        ev = self.by_title(d)["report: first step"]
        self.assertIsNone(ev["cost"])
        self.assertEqual(ev["cost_note"], flowcost.Note.TRUNCATED.format(cap=cap))

    def test_payload_carries_cost_fields(self):
        self.log(SID, self.rows((10, 0), (10, 12)))
        idx = tokens.TokenIndex(self.logs)
        idx.refresh()
        self.httpd.app.tokens = idx.snapshot      # what run() passes: the index's bound snapshot method
        status, _h, body = self.get(f"/api/flow/task/{TASK}.json")
        self.assertEqual(status, 200)
        d = json.loads(body)
        self.assertEqual(d["totals"]["cost_as_of"], prices.PRICES_AS_OF)
        self.assertIsNotNone(d["totals"]["cost"])
        coders = next(n for n in d["nodes"] if n["id"] == flow.Node.CODERS)
        self.assertIsNotNone(coders["tokens"])
        steps = [e for e in d["events"] if e["from"] == CODER]
        self.assertTrue(steps and all(e["cost"] is not None for e in steps))


if __name__ == "__main__":
    unittest.main()
