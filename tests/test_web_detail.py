"""G-019 B5: /goals, /goal/<id> and /task/<id> through the real server (web/views/goals.py, web/views/tasks.py)."""
import json
import re
import sqlite3
import statistics
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_web_queries import ts  # noqa: E402
from test_web_server import ServerCase  # noqa: E402
from web import html as wh  # noqa: E402

T_INS = "INSERT INTO tasks(id,goal_id,team_id,title,spec,acceptance,role,status,assignee,pr_url,attempts,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"
E_INS = "INSERT INTO events(ts,actor,entity,entity_id,action,detail) VALUES(?,?,?,?,?,?)"
V_INS = "INSERT INTO verdicts(task_id,pr_url,head_sha,role,verdict,summary,author,created) VALUES(?,?,?,?,?,?,?,?)"
A_INS = ("INSERT INTO agents(name,role,goal_id,team_id,task_id,status,model,started,ended) VALUES(?,?,?,?,?,?,?,?,?)")


class DetailCase(ServerCase):
    def page(self, path):
        status, _h, body = self.get(path)
        self.assertEqual(status, 200, path)
        return body.decode()

    def h1(self, path):
        return re.search(r"<h1>(.*?)</h1>", self.page(path), re.S).group(1)

    def seed_three_attempts(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-70','p1','Cycle goal','intent','1. a\n2. b','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-70", "G-70", None, "Three tries", "s", "a", "coder", "done", "coder-t-70", "https://github.com/o/r/pull/70", 3,
                  ts(9, 0), ts(12, 0), ))
        for name, a, b in (("coder-70a", (10, 0), (10, 30)), ("coder-70b", (10, 50), (11, 10)), ("coder-70c", (11, 30), (12, 0))):
            x(A_INS, (name, "coder", "G-70", None, "T-70", "done", "m", ts(*a), ts(*b)))
        x(V_INS, ("T-70", "u", "aaaaaaaa11", "reviewer", "fail", "needs work", "reviewer-70", ts(10, 40)))
        x(E_INS, (ts(11, 20, 5), "judge", "task", "T-70", "judge-reject", "bad"))             # same second as the judge fail row
        x(V_INS, ("T-70", "u", "bbbbbbbb22", "judge", "fail", "bad", "judge", ts(11, 20, 5)))
        x(V_INS, ("T-70", "u", "cccccccc33", "qa", "pass", "ok", "qa-70", ts(11, 50)))
        x(V_INS, ("T-70", "u", "cccccccc33", "judge", "merge", "ok", "judge", ts(12, 0)))
        x(E_INS, (ts(12, 0), "judge", "task", "T-70", "merged", "@deadbeef"))


class TestHeadings(DetailCase):
    def test_goal_h1_is_the_title_and_breadcrumb_links_goals(self):
        self.assertEqual(self.h1("/goal/G-1"), "Goal one")
        page = self.page("/goal/G-1")
        nav = re.search(r'<nav aria-label="Breadcrumb".*?</nav>', page, re.S).group(0)
        self.assertIn('href="/goals"', nav)
        self.assertIn("G-1", nav)

    def test_task_h1_is_the_title_and_breadcrumb_links_tasks(self):
        self.assertEqual(self.h1("/task/T-1"), "[SC1] one")
        nav = re.search(r'<nav aria-label="Breadcrumb".*?</nav>', self.page("/task/T-1"), re.S).group(0)
        self.assertIn('href="/tasks"', nav)

    def test_h1_follows_each_request_not_the_last_one(self):
        self.assertEqual(self.h1("/goal/G-1"), "Goal one")
        self.assertEqual(self.h1("/goal/G-2"), "Goal two")
        self.assertEqual(self.h1("/goal/G-404"), "Goal")


class TestNotFound(DetailCase):
    def test_unknown_goal_and_task_are_calm(self):
        goal, task = self.page("/goal/G-999"), self.page("/task/T-9999")
        self.assertIn("No goal G-999", goal)
        self.assertIn('href="/goals"', goal)
        self.assertIn("No task T-9999", task)
        self.assertIn('href="/tasks"', task)
        for page in (goal, task):
            self.assertNotIn("Traceback", page)


class TestAttempts(DetailCase):
    def test_three_attempts_latest_open_and_duplicate_pair_merged(self):
        self.seed_three_attempts()
        page = self.page("/task/T-70")
        blocks = re.findall(r'<details class="disc attempt"[^>]*>', page)
        self.assertEqual(len(blocks), 3)
        self.assertEqual([b.endswith(" open>") for b in blocks], [False, False, True])
        lines = re.findall(r'<li class="timeline-item" data-actor="([^"]*)" data-kind="([^"]*)" data-ts="([^"]*)"', page)
        for a, b in zip(lines, lines[1:]):
            self.assertNotEqual(a, b)
        at = ts(11, 20, 5)
        self.assertEqual(sum(1 for _a, k, t in lines if t == at), 1)        # judge-reject event + judge fail verdict: one line
        self.assertIn("Attempt 3", page)

    def test_verdict_summary_one_line_kinds_only(self):
        self.seed_three_attempts()
        page = self.page("/task/T-70")
        self.assertIn("Reviewer failed", page)
        self.assertIn("QA passed", page)
        self.assertIn("Judge rejected once, then merged", page)
        self.assertNotIn("needs work", page)

    def test_tiles_total_rejections_attempts(self):
        self.seed_three_attempts()
        page = self.page("/task/T-70")
        for label in ("Total time", "Rejections", "Attempts"):
            self.assertIn(label, page)

    def test_task_without_events_has_an_empty_cycle(self):
        self.con.execute(T_INS, ("T-71", "G-1", None, "fresh", "s", "a", "coder", "todo", None, None, 0, ts(9, 0), ts(9, 0)))
        page = self.page("/task/T-71")
        self.assertIn("No events yet.", page)
        self.assertIn("No verdicts yet.", page)


class TestPrivateText(DetailCase):
    def test_no_private_text_on_goals_goal_or_task(self):
        x = self.con.execute
        x("INSERT INTO messages(sender,recipient,kind,subject,body,goal_id,task_id,created,read_at) VALUES"
          "('lead-a','owner','escalation','SUBJECT-VISIBLE','BODY-SECRET','G-1',NULL,?,NULL)", (ts(9, 0),))
        x("INSERT INTO plans(goal_id,version,body,author,created) VALUES('G-1',2,'PLAN-SECRET','pm',?)", (ts(9, 0),))
        x("UPDATE tasks SET spec='SPEC-SECRET', acceptance='ACC-SECRET' WHERE id='T-1'")
        x(E_INS, (ts(9, 5), "lead", "task", "T-1", "note", "NOTE-SECRET"))
        x(V_INS, ("T-1", "u", "dddddddd44", "qa", "pass", "VERDICT-SECRET", "qa-1", ts(9, 6)))
        pages = {p: self.page(p) for p in ("/goals", "/goal/G-1", "/task/T-1")}
        for p, page in pages.items():
            for secret in ("BODY-SECRET", "PLAN-SECRET", "SPEC-SECRET", "ACC-SECRET", "NOTE-SECRET", "VERDICT-SECRET"):
                self.assertNotIn(secret, page, f"{secret} on {p}")
        self.assertIn("SUBJECT-VISIBLE", pages["/goals"])

    def test_privacy_rules_stay_in_the_view_docstrings(self):
        self.assertIn("Never renders plan bodies", (ROOT / "web/views/goals.py").read_text())
        self.assertIn("Never renders specs, acceptance text, notes or verdict summaries", (ROOT / "web/views/tasks.py").read_text())


class TestCriteria(DetailCase):
    def test_criteria_counts_only_for_tagged_goals(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-80','p1','Tagged goal',NULL,'1. one\n2. two','active',3,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-80", "G-80", None, "[SC1] done part", "s", "a", "coder", "done", None, None, 1, ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-81", "G-80", None, "[SC2] open part", "s", "a", "coder", "todo", None, None, 0, ts(8, 0), ts(9, 0)))
        x("INSERT INTO goals VALUES('G-81','p1','Untagged goal',NULL,'1. one','active',3,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-82", "G-81", None, "plain task", "s", "a", "coder", "done", None, None, 1, ts(8, 0), ts(9, 0)))
        page = self.page("/goals")
        rows = {m.group(1): m.group(0) for m in re.finditer(r'<li class="goalrow">.*?<span class="mono lrow-id">(G-\d+)</span>.*?</li>', page, re.S)}
        self.assertIn("criteria 1/2", rows["G-80"])
        self.assertNotIn("criteria", rows["G-81"])


    def test_list_and_detail_agree_for_a_done_but_unmerged_task(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-82','p1','Unmerged goal',NULL,'1. one\n2. two','active',3,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-83", "G-82", None, "[SC1] done, never merged", "s", "a", "coder", "done", None, None, 1, ts(8, 0), ts(9, 0)))
        x(T_INS, ("T-84", "G-82", None, "[SC2] open", "s", "a", "coder", "todo", None, None, 0, ts(8, 0), ts(9, 0)))
        self.assertIn("criteria 1/2", self.page("/goals"))
        self.assertIn("1/2 criteria", self.page("/goal/G-82"))


class TestGoalsPage(DetailCase):
    def order(self, path):
        return re.findall(r'<span class="mono lrow-id">(G-\d+)</span>', re.split(r'data-key="goals-done"', self.page(path))[0])

    def test_sort_whitelist(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-90','p1','Zero','i',NULL,'active',0,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        default = self.order("/goals")
        self.assertEqual(self.order("/goals?sort=nonsense"), default)
        self.assertEqual(self.order("/goals?sort=priority")[0], "G-90")
        self.assertEqual(self.order("/goals?sort=progress")[0], "G-1")      # the only goal with done work among the open ones

    def test_header_chips_and_sections(self):
        page = self.page("/goals")
        for word in ("Active", "Blocked", "Proposed", "Done", "Needs you", "Open goals"):
            self.assertIn(word, page)
        self.assertIn('data-key="goals-done"', page)

    def test_goal_detail_sections(self):
        page = self.page("/goal/G-1")
        for word in ("What&#x27;s blocking", "Success criteria", "Tasks", "Intent", "Teams", "v1"):
            self.assertIn(word, page)
        self.assertNotIn("What&#x27;s blocking", self.page("/goal/G-2"))


class TestContract(DetailCase):
    def test_api_goals_keeps_its_keys(self):
        status, _h, body = self.get("/api/goals.json")
        self.assertEqual(status, 200)
        self.assertTrue({"goals", "owner_pending", "internal_blocked"} <= set(json.loads(body)))

    def test_only_known_classes_and_no_inline_style(self):
        self.seed_three_attempts()
        for p in ("/goals", "/goal/G-1", "/task/T-1", "/task/T-70", "/goal/G-404"):
            page = self.page(p)
            used = {c for m in re.findall(r'class="([^"]*)"', page) for c in m.split()}
            self.assertEqual(used - wh.CLASSES, set(), p)
            self.assertNotIn("style=", page)

    def test_css_section_uses_tokens_only(self):
        css = (ROOT / "web/static/app.css").read_text()
        self.assertEqual(css.count("/* == B5 detail == */"), 1)
        sec = css.split("/* == B5 detail == */")[1]
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", sec))


class TestTaskCost(DetailCase):
    """T-1113: the cost line on /task/<id>, from the TokenIndex snapshot like /tokens."""

    def row(self, sid, model, inp=1_000_000, out=0):
        return {"session": sid, "model": model, "day": "2026-11-05", "fast": False, "input": inp, "output": out,
                "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "requests": 1}

    def seed(self, rows, org="claude", snap_ready=True):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-80','p1','Cost goal','intent','1. a','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(9, 0)))
        if org != "claude":
            x("ALTER TABLE goals ADD COLUMN org TEXT")
            x("UPDATE goals SET org=? WHERE id='G-80'", (org,))
        x(T_INS, ("T-80", "G-80", None, "Priced", "s", "a", "coder", "done", "coder-t-80", None, 1, ts(9, 0), ts(12, 0)))
        x("INSERT INTO agents(name,role,goal_id,team_id,task_id,status,model,session_id,started,ended) VALUES(?,?,?,?,?,?,?,?,?,?)",
          ("coder-80", "coder", "G-80", None, "T-80", "done", "m", "sess-80", ts(10, 0), ts(11, 0)))
        self.con.commit()
        sessions = {r["session"]: {"first_ts": ts(10, 0), "project": "", "cwd": "", "agent_name": None} for r in rows}
        snap = {"ready": snap_ready, "rows": rows, "sessions": sessions}
        self.httpd.app.tokens = lambda: snap

    def cost_line(self):
        return re.search(r"<p class=\"muted\">(Cost:.*?)</p>", self.page("/task/T-80"), re.S).group(1)

    def test_figure_matches_the_by_task_rollup_and_says_list_price(self):
        from web.tokens import attribute, rollup
        self.seed([self.row("sess-80", "claude-opus-5-5", 1_000_000, 100_000), self.row("other", "claude-opus-5-5")])
        snap = self.httpd.app.tokens()
        self.con.row_factory = sqlite3.Row
        want = rollup(snap, attribute(snap, self.con))["by_task"]["T-80"]["cost"]
        self.assertAlmostEqual(want, 6.0)
        line = self.cost_line()
        self.assertIn(f"${want:.2f}", line)
        self.assertIn("list prices", line)
        self.assertIn("estimated", line)

    def test_index_not_ready_and_no_tokens_callable_give_200_not_ready(self):
        self.seed([self.row("sess-80", "claude-opus-5-5")], snap_ready=False)
        self.assertIn("not ready", self.cost_line())
        self.httpd.app.tokens = None
        self.assertIn("not ready", self.cost_line())

    def test_no_attributed_tokens_says_none_recorded_not_zero(self):
        self.seed([self.row("unrelated", "claude-opus-5-5")])
        line = self.cost_line()
        self.assertIn("none recorded", line)
        self.assertNotIn("$0", line)

    def test_unpriced_model_says_unknown_never_a_guess(self):
        self.seed([self.row("sess-80", "mystery-model-9")])
        line = self.cost_line()
        self.assertIn("unknown", line)
        self.assertNotRegex(line, r"\$\d")

    def test_partly_unpriced_says_unknown_with_a_floor(self):
        self.seed([self.row("sess-80", "claude-opus-5-5"), self.row("sess-80", "mystery-model-9")])
        line = self.cost_line()
        self.assertIn("unknown", line)
        self.assertIn("at least $4.00", line)

    def test_cursor_org_goal_has_no_cost_figure(self):
        self.seed([self.row("sess-80", "claude-opus-5-5")], org="cursor")
        line = self.cost_line()
        self.assertIn("Cursor", line)
        self.assertNotRegex(line, r"\$\d")

    def test_large_snapshot_keeps_the_task_page_under_one_second(self):
        self.seed([self.row("sess-80", "claude-opus-5-5")] + [self.row(f"s{i}", "claude-opus-5-5") for i in range(3000)])
        runs = []
        for _ in range(3):
            t = time.perf_counter()
            self.assertIn("Cost: $4.00", self.cost_line())
            runs.append(time.perf_counter() - t)
        self.assertLess(statistics.median(runs), 1.0)


class TestSpeed(DetailCase):
    def test_median_render_under_200ms(self):
        self.seed_three_attempts()
        for p in ("/goals", "/goal/G-1", "/task/T-70"):
            runs = []
            for _ in range(5):
                t = time.perf_counter()
                self.page(p)
                runs.append(time.perf_counter() - t)
            self.assertLess(statistics.median(runs), 0.2, p)


if __name__ == "__main__":
    unittest.main()


M_INS = "INSERT INTO messages(sender,recipient,kind,subject,body,goal_id,task_id,created,read_at) VALUES(?,?,?,?,?,?,?,?,NULL)"


class TestFlow(DetailCase):
    """DVDG-544: the task flow diagram on /task/<id> (web/charts.flow_diagram, queries.task_flow)."""

    def seed_flow(self, live_judge=False, merged=False):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-80','p1','Flow goal','intent','1. a','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(8, 0)))
        x(T_INS, ("T-80", "G-80", "g-80-a", "Flow task", "SPEC-SECRET", "ACC-SECRET", "coder",
                  "done" if merged else "in_review", "coder-80", "https://github.com/o/r/pull/80", 2, ts(9, 0), ts(10, 40)))
        x(A_INS, ("coder-80", "coder", "G-80", "g-80-a", "T-80", "done", "m", ts(9, 10), ts(9, 40)))
        x(E_INS, (ts(9, 40), "coder-80", "task", "T-80", "update", "status=in_review pr=https://github.com/o/r/pull/80"))
        x(M_INS, ("coder-80", "lead-g-80-a", "report", "blocked: git identity", "BODY-SECRET", "G-80", "T-80", ts(9, 30)))
        x(V_INS, ("T-80", "u", "aaaaaaaa11", "reviewer", "fail", "SUMMARY-SECRET", "reviewer-80", ts(9, 50)))
        x(E_INS, (ts(10, 0), "lead-g-80-a", "task", "T-80", "update", "status=in_progress"))
        x(A_INS, ("lead-g-80-a", "lead", "G-80", "g-80-a", None, "live", "m", ts(8, 30), None))
        x(M_INS, ("lead-g-80-a", "coder-80b", "decision", "fix the review findings", "FIX-BODY", "G-80", "T-80", ts(9, 55)))
        x(A_INS, ("coder-80b", "coder", "G-80", "g-80-a", "T-80", "done", "m", ts(10, 0), ts(10, 20)))
        x(E_INS, (ts(10, 20), "coder-80b", "task", "T-80", "update", "status=in_review"))
        x(V_INS, ("T-80", "u", "bbbbbbbb22", "reviewer", "pass", "SUMMARY-SECRET", "reviewer-80b", ts(10, 30)))
        x(V_INS, ("T-80", "u", "bbbbbbbb22", "qa", "pass", "SUMMARY-SECRET", "qa-80", ts(10, 35)))
        if live_judge:
            x(A_INS, ("judge-80", "judge", "G-80", "g-80-a", "T-80", "live", "m", ts(10, 40), None))
        if merged:
            x(V_INS, ("T-80", "u", "bbbbbbbb22", "judge", "merge", "SUMMARY-SECRET", "judge", ts(10, 50)))
            x(E_INS, (ts(10, 50), "judge", "task", "T-80", "merged", "@cafebabe"))

    def states(self, page):
        """{stage label: state} from each node's class and the start of its <title>."""
        return {label: state for state, label in re.findall(r'class="flow-node flow-node--(\w+)[^"]*"><title>([^:<]+):', page)}

    def test_task_diagram_links_highlight_blocks(self):
        self.seed_flow()
        page = self.page("/task/T-80")
        for anchor in ("flow-s-goal", "flow-s-coding", "flow-in-coding", "flow-s-review"):
            self.assertIn(f'href="#{anchor}"', page)             # a node, the arrow into Coding, the rejection loop
            self.assertIn(f'id="{anchor}"', page)               # the block the click highlights (CSS :target)
        block = page[page.index('id="flow-in-coding"'):]
        self.assertIn("lead-g-80-a → coder-80b (decision): fix the review findings", block[:400])
        self.assertNotIn("FIX-BODY", page)                     # text stays hidden without serve_show_text

    def test_goal_page_shows_who_instructed_whom(self):
        self.seed_flow()
        self.seed_hq_chain()
        page = self.page("/goal/G-80")
        self.assertIn("<h2>Flow", page)
        for anchor in ("gf-e-boss-director", "gf-e-director-lead", "gf-e-lead-coder", "gf-n-coder", "gf-n-lead"):
            self.assertIn(f'href="#{anchor}"', page)
            self.assertIn(f'id="{anchor}"', page)
        self.assertIn("Boss ⇄ Director", page)
        self.assertIn("Coders · 2 agent(s)", page)
        self.assertIn("flow-node--current flow-node--live", page)   # the lead is live: its box pulses
        for secret in ("FIX-BODY", "BODY-SECRET", "Plan it with a pm."):
            self.assertNotIn(secret, page)
        self.con.execute("INSERT INTO config(key,value) VALUES('serve_show_text','1')")
        self.assertIn("Plan it with a pm.", self.page("/goal/G-80"))

    def test_current_step_pulses_always_and_clicks_highlight(self):
        css = (ROOT / "web/static/app.css").read_text()
        self.assertIn(".flow-node--current .flow-box { animation: flow-pulse-soft", css)
        self.assertIn(".flow-stage:target", css)

    def test_flow_marks_passed_current_and_pending(self):
        self.seed_flow()
        states = self.states(self.page("/task/T-80"))
        self.assertEqual(states, {"Goal (HQ)": "done", "Planned": "done", "Coding": "done", "Review / QA": "done", "Judge": "current",
                                  "Merged": "pending"})
        self.assertIn('aria-label="Task flow, now at: Judge"', self.page("/task/T-80"))

    def test_flow_shows_rejection_loop_and_time_per_stage(self):
        self.seed_flow()
        page = self.page("/task/T-80")
        self.assertIn("rejected 1× · 2 attempts", page)
        self.assertRegex(page, r'class="flow-time"[^>]*>\d')    # a duration under at least one stage

    def test_flow_tooltips_hold_facts_but_never_private_text(self):
        self.seed_flow()
        page = self.page("/task/T-80")
        self.assertIn("reviewer FAIL @aaaaaaaa", page)
        self.assertIn("coder-80 → lead-g-80-a (report): blocked: git identity", page)
        for secret in ("SUMMARY-SECRET", "BODY-SECRET", "SPEC-SECRET", "ACC-SECRET"):
            self.assertNotIn(secret, page)

    def test_flow_animates_only_with_a_live_agent(self):
        self.seed_flow()
        page = self.page("/task/T-80")
        self.assertNotIn("flow-node--live", page)
        self.assertNotIn("flow-edge--active", page)
        self.con.execute(A_INS, ("judge-80", "judge", "G-80", "g-80-a", "T-80", "live", "m", ts(10, 40), None))
        page = self.page("/task/T-80")
        self.assertIn("flow-node--current flow-node--live", page)
        self.assertIn("flow-edge--active", page)
        self.assertIn("● judge working", page)

    def test_merged_task_is_finished_and_not_animated(self):
        self.seed_flow(live_judge=False, merged=True)
        page = self.page("/task/T-80")
        self.assertIn('aria-label="Task flow, now at: finished"', page)
        self.assertNotIn("flow-node--current", page)
        self.assertIn("judge: merged @cafebabe", page)

    def test_flow_has_no_inline_style_or_script_and_known_classes(self):
        self.seed_flow(live_judge=True)
        page = self.page("/task/T-80")
        sec = page[page.index("<h2>Flow"):page.index("<h2>Verdicts")]
        self.assertNotIn("style=", sec)
        self.assertNotIn("<script", sec)
        used = {c for m in re.findall(r'class="([^"]*)"', page) for c in m.split()}
        self.assertEqual(used - wh.CLASSES, set())

    def seed_hq_chain(self):
        x = self.con.execute
        x(M_INS, ("boss", "director", "request", "new goal G-80", "## Goal\n- build **the flow**\n`code here`\n<script>x</script>",
                  "G-80", None, ts(8, 10)))
        x(M_INS, ("director", "lead-g-80-a", "request", "brief G-80", "Plan it with a pm.", "G-80", None, ts(8, 20)))
        x(M_INS, ("lead-g-80-a", "director", "report", "late goal report", "AFTER-TASK", "G-80", None, ts(11, 0)))

    def test_goal_stage_holds_the_hq_chain_before_the_task(self):
        self.seed_flow()
        self.seed_hq_chain()
        page = self.page("/task/T-80")
        self.assertIn("boss → director (request): new goal G-80", page)
        self.assertIn("director → lead-g-80-a (request): brief G-80", page)
        self.assertNotIn("late goal report", page)           # goal-level messages after the task was created are not its chain
        self.assertNotIn("build", page)                      # text stays hidden while serve_show_text is off

    def test_show_text_renders_instructions_as_markdown(self):
        self.seed_flow()
        self.seed_hq_chain()
        self.con.execute("INSERT INTO config(key,value) VALUES('serve_show_text','1')")
        page = self.page("/task/T-80")                        # the test server binds 127.0.0.1 (loopback)
        self.assertIn("<h5>Goal</h5>", page)
        self.assertIn("<li>build <strong>the flow</strong></li>", page)
        self.assertIn("<code>code here</code>", page)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", page)
        self.assertIn("SPEC-SECRET", page)                   # the task's spec: the plan's instructions to the worker
        self.assertIn("SUMMARY-SECRET", page)                # verdict summaries
        self.assertIn("BODY-SECRET", page)
        sec = page[page.index("<h2>Flow"):page.index("<h2>Verdicts")]
        self.assertNotIn("<script", sec)
        self.assertNotIn("style=", sec)

    def test_show_text_needs_loopback(self):
        from web import server
        self.assertTrue(server.show_text_allowed("127.0.0.1", "1"))
        self.assertTrue(server.show_text_allowed("::1", "1"))
        self.assertFalse(server.show_text_allowed("127.0.0.1", "0"))
        self.assertFalse(server.show_text_allowed("127.0.0.1", None))
        self.assertFalse(server.show_text_allowed("203.0.113.5", "1"))   # a non-loopback bind never shows text
        self.assertFalse(server.show_text_allowed("not-an-ip", "1"))


class TestMarkdown(unittest.TestCase):
    """web/html.md: the small Markdown renderer for instruction text (DVDG-544)."""

    def test_blocks_and_inline(self):
        out = str(wh.md("# Title\n\n1. one\n2. two\n\n> quoted\n\n```\nx < y\n```\n\n| a | b |\n|---|---|\n| 1 | *i* |\n\nsee [docs](https://example.com/x)"))
        self.assertIn("<h4>Title</h4>", out)
        self.assertIn("<ol><li>one</li><li>two</li></ol>", out)
        self.assertIn("<blockquote>quoted</blockquote>", out)
        self.assertIn("<pre><code>x &lt; y</code></pre>", out)
        self.assertIn("<th>a</th>", out)
        self.assertIn("<td><em>i</em></td>", out)
        self.assertIn('<a href="https://example.com/x" rel="noopener noreferrer">docs</a>', out)

    def test_never_emits_raw_html_or_unsafe_links(self):
        out = str(wh.md('<img src=x onerror=alert(1)> [x](javascript:alert(1)) <b>bold</b> "q"'))
        self.assertNotIn("<img", out)
        self.assertNotIn("<b>", out)
        self.assertNotIn('href="javascript', out)
        self.assertIn("&lt;img", out)
        self.assertNotIn(" style=", out)
        self.assertNotIn(" class=", out)


class TestFlowTimes(DetailCase):
    """DVDG-544 regressions from the live T-0003: a respawned coder and a reviewer FAIL next to a QA pass."""

    def seed_rework(self):
        x = self.con.execute
        x("INSERT INTO goals VALUES('G-81','p1','Rework goal','intent','1. a','active',2,'owner',NULL,?,?)", (ts(8, 0), ts(8, 0)))
        x(T_INS, ("T-81", "G-81", "g-81-a", "Rework task", "s", "a", "coder", "in_progress", "coder-t-81",
                  "https://github.com/o/r/pull/81", 2, ts(9, 0), ts(10, 43)))
        x(E_INS, (ts(9, 10), "lead-g-81-a", "task", "T-81", "task-auto-start", "spawn coder-t-81"))
        # the respawn reused the agent row: `started` now holds the second start, not the first
        x(A_INS, ("coder-t-81", "coder", "G-81", "g-81-a", "T-81", "live", "m", ts(10, 43), None))
        x(E_INS, (ts(9, 40), "coder-t-81", "task", "T-81", "update", "status=in_review pr=https://github.com/o/r/pull/81"))
        x(V_INS, ("T-81", "u", "cccccccc33", "reviewer", "fail", "bug", "reviewer-81", ts(10, 37)))
        x(V_INS, ("T-81", "u", "cccccccc33", "qa", "pass", "ok", "qa-81", ts(10, 42)))
        x(E_INS, (ts(10, 43), "lead-g-81-a", "task", "T-81", "update", "status=in_progress"))

    def node_time(self, page, label):
        m = re.search(rf'<text class="flow-label"[^>]*>{re.escape(label)}</text><text class="flow-time"[^>]*>([^<]*)<', page)
        return m.group(1) if m else None

    def test_respawn_keeps_the_first_coder_start(self):
        self.seed_rework()
        page = self.page("/task/T-81")
        self.assertEqual(self.node_time(page, "Planned"), "10m 00s")    # 09:00 created -> 09:10 first start, not 10:43
        self.assertEqual(self.node_time(page, "Coding"), "30m 00s")     # 09:10 -> 09:40 PR opened (was unknown)

    def test_reviewer_fail_with_qa_pass_never_reaches_the_judge(self):
        self.seed_rework()
        page = self.page("/task/T-81")
        states = {label: state for state, label in re.findall(r'class="flow-node flow-node--(\w+)[^"]*"><title>([^:<]+):', page)}
        self.assertEqual(states["Judge"], "pending")
        self.assertEqual(states["Coding"], "current")
        self.assertEqual(self.node_time(page, "Judge"), "")              # no time counted from the QA pass

    def test_goal_time_stops_where_the_pm_spec_work_starts(self):
        self.seed_rework()
        x = self.con.execute
        x(T_INS, ("P-81", "G-81", "g-81-a", "Plan the goal", "s", "a", "pm", "done", "pm-81", None, 2, ts(8, 50), ts(9, 0)))
        x(A_INS, ("pm-81", "pm", "G-81", "g-81-a", "P-81", "done", "m", ts(8, 50), ts(9, 0)))
        x(E_INS, (ts(9, 0), "pm-81", "task", "T-81", "add", "Rework task"))
        page = self.page("/task/T-81")
        self.assertEqual(self.node_time(page, "Goal (HQ)"), "50m 00s")   # 08:00 goal -> 08:50 PM starts the spec
        self.assertEqual(self.node_time(page, "Planned"), "20m 00s")     # spec 08:50-09:00 + queued 09:00-09:10

    def test_stage_left_without_a_verdict_stops_counting(self):
        self.seed_rework()
        x = self.con.execute
        x(E_INS, (ts(11, 0), "coder-t-81", "task", "T-81", "update", "status=in_review pr=https://github.com/o/r/pull/81"))
        x(E_INS, (ts(11, 15), "lead-g-81-a", "task", "T-81", "update", "status=todo — wait for the shared helper"))
        x("UPDATE tasks SET status='todo' WHERE id='T-81'")
        page = self.page("/task/T-81")
        states = {label: state for state, label in re.findall(r'class="flow-node flow-node--(\w+)[^"]*"><title>([^:<]+):', page)}
        self.assertEqual(states["Planned"], "current")
        self.assertEqual(self.node_time(page, "Review / QA"), "1h 17m")   # 09:40-10:42 + 11:00-11:15, not "until now"
