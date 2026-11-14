"""App shell (G-019 B2): every route renders the shared shell, the nav works without JS, nav badges mean only
"needs attention", enum labels are human, and shell_status picks the health state."""
import contextlib
import datetime as dt
import io
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_web_queries import make_db  # noqa: E402
from test_web_server import PAGES, ServerCase, get  # noqa: E402
from web import html as wh  # noqa: E402
from web import queries, server  # noqa: E402

NOW = dt.datetime(2026, 10, 27, 14, 52).astimezone()
SHELL = {"now": NOW, "needs": 0, "agents_attention": 0, "health": {"tone": "success", "text": "All normal"}}


def main_nav(text):
    m = re.search(r'<nav aria-label="Main".*?</nav>', text, re.S)
    assert m, "no Main nav"
    return m.group(0)


def nav_item(text, href):
    m = re.search(r'<a href="%s" class="nav-item[^"]*"[^>]*>.*?</a>' % re.escape(href), main_nav(text), re.S)
    assert m, f"no nav item {href}"
    return m.group(0)


class TestEveryRouteRenders(ServerCase):
    def test_twelve_routes_have_the_shell(self):
        self.assertEqual(len(PAGES), 12)   # HM-1 added /settings
        for path in PAGES:
            with self.subTest(path):
                code, _, body = self.get(path)
                text = body.decode()
                self.assertEqual(code, 200)
                self.assertIn('href="#content"', text)
                self.assertIn('<nav aria-label="Main"', text)
                self.assertIn("Updated ", text)
                self.assertEqual(text.count('aria-current="page"'), 1)
                self.assertIn('<main id="content"', text)

    def test_nav_has_all_ten_links_without_js(self):
        text = self.get("/")[2].decode()
        nav = main_nav(text)
        hrefs = re.findall(r'<a href="([^"]+)"', nav)
        self.assertEqual(hrefs[0], "/")   # the wordmark
        sections = re.findall(r'<a href="([^"]+)" class="nav-item', nav)   # HM-36: goal links sit under "Goals" too
        self.assertEqual(sections, [p for p, _ in wh.NAV])
        self.assertEqual(len(sections), 10)
        self.assertEqual(re.findall(r"<script\b[^>]*>", text), ['<script src="/static/theme.js" defer>'])

    def test_phone_more_nav_lists_every_page_and_tabbar_has_five_items(self):
        text = self.get("/tasks")[2].decode()
        more = re.search(r'<nav id="more".*?</nav>', text, re.S).group(0)
        self.assertEqual(len(re.findall(r'<a href="/[a-z]*"', more)), 10)
        tabs = re.search(r'<nav aria-label="Primary tabs".*?</nav>', text, re.S).group(0)
        self.assertEqual(len(re.findall(r"<a ", tabs)), 5)
        self.assertIn('href="#more"', tabs)

    def test_active_item_for_detail_pages_is_the_list(self):
        self.assertIn("nav-item--active", nav_item(self.get("/task/T-1")[2].decode(), "/tasks"))

    def test_tasks_use_human_labels_not_enums(self):
        text = self.get("/tasks")[2].decode()
        self.assertIn("In progress", text)
        self.assertNotIn(">in_progress<", text)
        self.assertNotIn(">in_review<", text)

    def test_header_cluster_shows_updated_time_health_and_needs_you(self):
        text = self.get("/goals")[2].decode()
        self.assertRegex(text, r'Updated <time datetime="[^"]+">\d\d:\d\d</time>')
        self.assertIn('class="pill hide-phone tone-', text)
        self.assertIn('href="/#needs-you"', text)   # the seed has blocked work and an unread escalation


class ShellDb(unittest.TestCase):
    """Server on an empty DB that each test fills."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = make_db(Path(self.tmp.name) / "factory.db", seed=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.usage = {"five_hour": 10.0, "seven_day": 20.0, "fresh": True, "age_min": 1}
        self.httpd = server.make_server(Path(self.tmp.name) / "factory.db", "127.0.0.1", 0, (), tokens=lambda: {"rows": []},
                                        usage_fn=lambda: self.usage, mem_fn=lambda: 2048,
                                        defaults={"max_live_agents": "6", "max_five_hour_pct": "92", "max_seven_day_pct": "92"})
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def get(self, path):
        with contextlib.redirect_stderr(io.StringIO()):
            return get(self.httpd, path)[2].decode()

    def agents(self, n, status, prefix="a"):
        for i in range(n):
            self.con.execute("INSERT INTO agents(name,role,status,started) VALUES(?,?,?,?)",
                             (f"{prefix}{i}", "coder", status, "2026-10-27T10:00:00+01:00"))

    def test_eight_running_agents_give_the_agents_nav_item_no_badge(self):
        self.agents(8, "live")
        text = self.get("/agents")
        self.assertNotIn('class="count', nav_item(text, "/agents"))
        self.assertNotIn('class="count', nav_item(text, "/"))
        self.assertNotIn("Needs you", text)

    def test_queued_agents_do_get_a_badge_and_blocked_work_badges_overview(self):
        self.agents(2, "queued", "q")
        self.con.execute("INSERT INTO projects(id,name,created) VALUES('p','P','x')")
        self.con.execute("INSERT INTO goals(id,project_id,title,status,priority,created,updated) "
                         "VALUES('G-1','p','g','blocked',1,'x','x')")
        for n in (1, 2):
            self.con.execute("INSERT INTO tasks(id,goal_id,title,status,waits,created,updated) VALUES(?,?,?,?,?,?,?)",
                             (f"T-{n}", "G-1", "t", "blocked", "owner", "x", "x"))
        text = self.get("/")
        agents_item = nav_item(text, "/agents")
        self.assertRegex(agents_item, r'<span class="count" aria-label="2 agents queued or blocked">2</span>')
        needs = queries.shell_status(self.con, None, None)["needs"]
        self.assertEqual(needs, 3)   # blocked goal + 2 owner-blocked tasks
        self.assertRegex(nav_item(text, "/"), r'class="count count--bad" aria-label="3 items need you">3<')
        self.assertEqual(re.findall(r'aria-label="3 items need you"[^>]*>Needs you 3<', text).__len__(), 2)  # top bar + header


class TestShellStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = make_db(Path(self.tmp.name) / "factory.db", seed=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.fresh = {"five_hour": 10.0, "seven_day": 20.0, "fresh": True, "age_min": 1}
        self.dflt = {"max_live_agents": "2", "max_five_hour_pct": "92"}

    def health(self, usage, defaults=None):
        return queries.shell_status(self.con, usage, self.dflt if defaults is None else defaults)["health"]

    def agents(self, n, status):
        for i in range(n):
            self.con.execute("INSERT INTO agents(name,role,status,started) VALUES(?,?,?,?)", (f"{status}{i}", "coder", status, "x"))

    def test_all_normal(self):
        self.assertEqual(self.health(self.fresh), {"tone": "success", "text": "All normal"})

    def test_gate_closed_counts_queued(self):
        self.agents(2, "live")
        self.agents(3, "queued")
        self.assertEqual(self.health(self.fresh), {"tone": "warning", "text": "Gate closed · 3 queued"})

    def test_usage_high_warns_and_cap_is_danger(self):
        self.assertEqual(self.health({**self.fresh, "five_hour": 85.0}), {"tone": "warning", "text": "Claude usage 85%"})
        self.assertEqual(self.health({**self.fresh, "five_hour": 95.0}), {"tone": "danger", "text": "Usage cap reached"})

    def test_weekly_cap_alone_is_danger(self):
        self.assertEqual(self.health({**self.fresh, "five_hour": 10.0, "seven_day": 95.0}),
                         {"tone": "danger", "text": "Usage cap reached"})

    def test_weekly_cap_uses_configured_threshold(self):
        u = {**self.fresh, "seven_day": 60.0}
        self.assertEqual(self.health(u)["tone"], "success")
        self.assertEqual(self.health(u, {**self.dflt, "max_seven_day_pct": "60"})["text"], "Usage cap reached")

    def test_five_hour_cap_alone_is_danger(self):
        self.assertEqual(self.health({**self.fresh, "five_hour": 92.0, "seven_day": 5.0})["text"], "Usage cap reached")

    def test_both_windows_under_is_normal(self):
        self.assertEqual(self.health({**self.fresh, "five_hour": 50.0, "seven_day": 50.0}),
                         {"tone": "success", "text": "All normal"})

    def test_weekly_warning_band(self):
        self.assertEqual(self.health({**self.fresh, "seven_day": 80.0}), {"tone": "warning", "text": "Weekly usage 80%"})
        self.assertEqual(self.health({**self.fresh, "seven_day": 73.0})["tone"], "success")

    def test_unknown_or_stale_usage_is_neutral_not_green(self):
        self.assertEqual(self.health(None)["tone"], "neutral")
        self.assertEqual(self.health({**self.fresh, "age_min": 45})["tone"], "neutral")
        self.assertEqual(self.health({"unreadable": True})["tone"], "neutral")

    def test_cap_over_config_wins_over_default(self):
        self.agents(2, "live")
        self.con.execute("INSERT INTO config VALUES('max_live_agents','9')")
        self.assertEqual(self.health(self.fresh)["tone"], "success")

    def test_running_agents_never_count_as_attention(self):
        self.agents(8, "live")
        self.assertEqual(queries.shell_status(self.con, self.fresh, self.dflt)["agents_attention"], 0)
        self.agents(1, "queued")
        self.assertEqual(queries.shell_status(self.con, self.fresh, self.dflt)["agents_attention"], 1)


class TestHelpers(unittest.TestCase):
    def test_status_is_glyph_plus_human_label(self):
        out = str(wh.status("in_progress"))
        self.assertIn("In progress", out)
        self.assertNotIn(">in_progress<", out)
        self.assertIn('aria-hidden="true"', out)

    def test_shapes_separate_todo_from_cancelled_and_progress_from_review(self):
        g = {k: str(wh.glyph(k)) for k in ("todo", "cancelled", "in_progress", "in_review")}
        self.assertEqual(len(set(g.values())), 4)
        self.assertIn("fg-review", str(wh.status("in_review")))

    def test_every_label_maps_every_status_enum(self):
        for s in wh._STATUSES:
            with self.subTest(s):
                self.assertIn(s, wh.LABELS)
                self.assertIn(s, wh._SVG12)

    def test_breadcrumb_marks_last_item_and_keeps_one_aria_current_page(self):
        out = str(wh.crumbs(("/goals", "Goals"), ("/goal/G-1", "G-1")))
        self.assertIn('<nav aria-label="Breadcrumb"', out)
        self.assertIn('<a href="/goals">Goals</a>', out)
        self.assertIn('<span aria-current="location">G-1</span>', out)
        doc = wh.page("G-1", "<p>x</p>", "/goals", shell=SHELL, crumb_trail=wh.crumbs(("/goals", "Goals"), ("/goal/G-1", "G-1")))
        self.assertEqual(doc.count('aria-current="page"'), 1)

    def test_page_without_shell_data_still_has_skip_link_and_nav(self):
        doc = wh.page("Error", "<p>x</p>", "")
        self.assertIn('<a href="#content" class="skip">', doc)
        self.assertIn('<nav aria-label="Main"', doc)
        self.assertNotIn('aria-current="page"', doc)

    def test_updated_time_is_the_injected_now(self):
        self.assertIn(f'<time datetime="{NOW.isoformat(timespec="minutes")}">14:52</time>', wh.page("T", "", "/", shell=SHELL))

    def test_zero_needs_you_hides_the_badge(self):
        self.assertNotIn("Needs you", wh.page("T", "", "/", shell=SHELL))
        self.assertIn("Needs you 4", wh.page("T", "", "/", shell={**SHELL, "needs": 4}))



def block(text, pattern):
    m = re.search(pattern, text, re.S)
    assert m, f"no block {pattern}"
    return m.group(0)


class TestPhoneNeedsOnce(ShellDb):
    def seed_needs(self):
        self.con.execute("INSERT INTO projects(id,name,created) VALUES('p','P','x')")
        self.con.execute("INSERT INTO goals(id,project_id,title,status,priority,created,updated) "
                         "VALUES('G-1','p','g','blocked',1,'x','x')")
        for n in (1, 2):
            self.con.execute("INSERT INTO tasks(id,goal_id,title,status,waits,created,updated) VALUES(?,?,?,?,?,?,?)",
                             (f"T-{n}", "G-1", "t", "blocked", "owner", "x", "x"))

    def test_tab_bar_has_no_needs_you_count_but_topbar_has_one(self):
        self.seed_needs()
        self.agents(2, "queued", "q")
        text = self.get("/")
        tabs = block(text, r'<nav aria-label="Primary tabs".*?</nav>')
        self.assertNotIn("items need you", tabs)
        self.assertNotIn("count--bad", tabs)
        top = block(text, r'<header class="topbar".*?</header>')
        self.assertEqual(top.count('aria-label="3 items need you"'), 1)

    def test_other_counts_are_kept(self):
        self.seed_needs()
        self.agents(2, "queued", "q")
        text = self.get("/")
        tabs = block(text, r'<nav aria-label="Primary tabs".*?</nav>')
        self.assertRegex(tabs, r'<span class="count" aria-label="2 agents queued or blocked">2</span>')
        self.assertRegex(nav_item(text, "/"), r'class="count count--bad" aria-label="3 items need you">3<')
        self.assertIn('aria-label="3 items need you"', block(text, r'<header class="shellbar".*?</header>'))


class TestR1ShellCss(unittest.TestCase):
    CSS = (ROOT / "web" / "static" / "app.css").read_text()

    def test_phone_shellbar_stacks_and_desktop_rule_is_unchanged(self):
        phone = "".join(re.findall(r"@media \(max-width: 639px\) \{(.*?)\n\}", self.CSS, re.S))
        self.assertRegex(phone, r"\.shellbar \{[^}]*flex-direction: column")
        self.assertRegex(self.CSS, r"\n\.shellbar \{ display: flex; align-items: flex-start; justify-content: space-between;")

    def test_seg_links_do_not_wrap_and_scroll_inside_themselves(self):
        self.assertRegex(self.CSS, r"\.seg-links \{[^}]*max-width: 100%; overflow-x: auto")
        self.assertRegex(self.CSS, r"\.seg-links a \{[^}]*white-space: nowrap")

    def test_seg_links_focus_ring_is_drawn_inside_the_scroll_box(self):
        self.assertRegex(self.CSS, r"\.seg-links a:focus-visible \{ outline-offset: -2px; \}")
        self.assertRegex(self.CSS, r"\.ins-check--over \{[^}]*padding: 0 var\(--s2\)")

    def test_more_list_hidden_until_targeted_and_tab_still_points_at_it(self):
        self.assertRegex(self.CSS, r"\n\.more \{ display: none;")
        self.assertRegex(self.CSS, r"\n\.more:target \{ display: block; \}")
        self.assertRegex(self.CSS, r"\.tabbar, \.more, \.more:target \{ display: none; \}")   # still hidden from 640 px up
        self.assertRegex(self.CSS, r"\.topbar, \.tabbar, \.more, \.more:target \{ display: none; \}")
        self.assertIn("Theme", wh._shell_navs("/tasks", SHELL)[1].__str__())


class TestMemoryLow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = make_db(Path(self.tmp.name) / "factory.db", seed=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.fresh = {"five_hour": 10.0, "seven_day": 20.0, "fresh": True, "age_min": 1}
        self.dflt = {"max_live_agents": "2", "max_five_hour_pct": "92"}

    def health(self, usage):
        return queries.shell_status(self.con, usage, self.dflt)["health"]

    def agents(self, n, status):
        for i in range(n):
            self.con.execute("INSERT INTO agents(name,role,status,started) VALUES(?,?,?,?)", (f"{status}{i}", "coder", status, "x"))

    def mem_health(self, mem, usage=None, defaults=None):
        return queries.shell_status(self.con, usage or self.fresh, defaults or {**self.dflt, "min_mem_available_mb": "1024"},
                                    mem=mem)["health"]

    def test_below_floor_is_danger(self):
        self.assertEqual(self.mem_health(500), {"tone": "danger", "text": "Memory low"})

    def test_floor_itself_is_not_low(self):
        self.assertNotEqual(self.mem_health(1024)["text"], "Memory low")

    def test_unknown_mem_changes_nothing(self):
        self.assertEqual(self.mem_health(None), self.health(self.fresh))

    def test_memory_low_is_worse_than_usage_cap(self):
        self.assertEqual(self.mem_health(500, {**self.fresh, "five_hour": 95.0})["text"], "Memory low")

    def test_plenty_of_memory_leaves_gate_closed(self):
        self.agents(2, "live")
        self.assertTrue(self.mem_health(4000)["text"].startswith("Gate closed"))

    def test_floor_falls_back_to_1024_and_follows_config(self):
        self.assertEqual(queries.shell_status(self.con, self.fresh, None, mem=1000)["health"]["text"], "Memory low")
        self.assertEqual(self.mem_health(1000, defaults={"min_mem_available_mb": "512"})["text"], "All normal")


class TestMemoryLowServed(unittest.TestCase):
    def page(self, mem):
        with tempfile.TemporaryDirectory() as tmp:
            make_db(Path(tmp) / "factory.db").close()
            httpd = server.make_server(Path(tmp) / "factory.db", "127.0.0.1", 0, (), tokens=lambda: {"rows": []},
                                       usage_fn=lambda: {"five_hour": 10.0, "seven_day": 20.0, "fresh": True, "age_min": 1},
                                       mem_fn=lambda: mem, defaults={"max_live_agents": "99"})
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    return get(httpd, "/tasks")[2].decode()
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_low_memory_shows_danger_pill(self):
        text = self.page(100)
        self.assertIn("Memory low", text)
        self.assertIn("tone-danger", text)

    def test_plenty_of_memory_does_not(self):
        self.assertNotIn("Memory low", self.page(999999))


class TestSidebarGoals(ShellDb):
    """HM-36: active goals under "Goals" with the Goals page's indicators, and a "+" with the last 5 done goals."""

    def setUp(self):
        super().setUp()
        self.con.execute("INSERT INTO projects(id,name,created) VALUES('psb','P','x')")

    def goal(self, gid, status, prio=2, updated="2026-10-01T10:00:00+00:00", done=0, total=0, closed=None, org=None):
        self.con.execute("INSERT INTO goals(id,project_id,title,status,priority,created,updated) VALUES(?,?,?,?,?,?,?)",
                         (gid, "psb", f"Title of {gid}", status, prio, "x", updated))
        for n in range(total):
            self.con.execute("INSERT INTO tasks(id,goal_id,title,status,created,updated) VALUES(?,?,?,?,?,?)",
                             (f"T-{gid}-{n}", gid, "t", "done" if n < done else "todo", "x", "x"))
        if closed:
            self.con.execute("INSERT INTO events(ts,actor,entity,entity_id,action,detail) VALUES(?,?,?,?,?,?)",
                             (closed, "boss", "goal", gid, "status", "done"))
        if org:
            self.con.execute("UPDATE goals SET org=? WHERE id=?", (org, gid))

    @staticmethod
    def sub(text, cls="navsub"):
        m = re.search(r'<ul class="%s">.*?</ul>' % cls, main_nav(text), re.S)
        return m.group(0) if m else ""

    def test_only_active_goals_with_the_goals_page_indicators(self):
        from web import charts
        from web.components import row_status

        self.goal("G-001", "done", closed="2026-10-02T10:00:00+00:00")
        self.goal("G-002", "active", done=11, total=12)
        self.goal("G-003", "planning")
        self.goal("G-004", "blocked")
        active = self.sub(self.get("/tasks"))
        self.assertEqual(re.findall(r'href="/goal/(G-\d+)"', active), ["G-002"])
        self.assertIn(str(row_status("active")), active)
        self.assertIn(str(charts.meter(11, 12, "11/12 tasks")), active)
        self.assertIn('aria-label="Active, G-002, Title of G-002, 11 of 12 tasks done"', active)

    def test_plus_lists_the_five_done_goals_closed_last_newest_first(self):
        self.goal("G-010", "active")
        for n in range(1, 7):   # closed on Oct 1..6 by their status event
            self.goal(f"G-10{n}", "done", closed=f"2026-10-0{n}T10:00:00+00:00", updated="2026-09-01T00:00:00+00:00")
        self.goal("G-200", "done", updated="2026-10-04T12:00:00+00:00")   # no status event: placed by updated
        nav = main_nav(self.get("/tasks"))
        plus = re.search(r'<summary class="navplus"[^>]*>', nav).group(0)
        self.assertIn('aria-label="Show the last 5 done goals"', plus)
        self.assertIn('aria-expanded="false"', plus)
        self.assertLess(nav.index('class="navplus"'), nav.index('<ul class="navsub navsub--done">'))
        done = self.sub(self.get("/tasks"), "navsub navsub--done")
        self.assertEqual(re.findall(r'href="/goal/(G-\d+)"', done), ["G-106", "G-105", "G-200", "G-104", "G-103"])

    def test_done_goals_open_by_themselves_when_no_goal_is_active(self):  # owner follow-up 2026-11-14
        self.goal("G-001", "done", closed="2026-10-02T10:00:00+00:00")
        self.goal("G-002", "planning")
        nav = main_nav(self.get("/tasks"))
        self.assertRegex(nav, r'<details class="navdone" data-key="nav-done-goals" open>')
        self.assertIn('aria-label="Hide done goals" aria-expanded="true"', nav)
        self.goal("G-003", "active")
        self.assertNotRegex(main_nav(self.get("/tasks")), r'<details class="navdone"[^>]* open>')

    def test_no_done_goal_no_plus_and_no_goals_no_lists(self):
        self.assertNotIn("navsub", main_nav(self.get("/tasks")))
        self.goal("G-002", "active", done=0, total=0)
        nav = main_nav(self.get("/tasks"))
        self.assertNotIn("navplus", nav)
        self.assertIn("0/0 tasks", self.sub(self.get("/tasks")))

    def test_org_filter_is_kept_and_other_orgs_are_left_out(self):
        self.con.execute("ALTER TABLE goals ADD COLUMN org TEXT NOT NULL DEFAULT 'claude'")
        self.goal("G-002", "active", org="claude")
        self.goal("G-005", "active", org="cursor")
        self.goal("G-006", "done", closed="2026-10-02T10:00:00+00:00", org="cursor")
        self.goal("G-007", "done", closed="2026-10-03T10:00:00+00:00", org="claude")
        nav = main_nav(self.get("/tasks?org=cursor"))
        self.assertEqual(re.findall(r'href="/goal/(G-\d+)\?org=cursor"', nav), ["G-005", "G-006"])
        self.assertNotIn("G-002", nav)
        self.assertNotIn("G-007", nav)

    def test_current_goal_is_marked_and_a_done_one_opens_the_list(self):
        self.goal("G-002", "active", done=1, total=2)
        self.goal("G-001", "done", closed="2026-10-02T10:00:00+00:00")
        text = self.get("/goal/G-002")
        self.assertRegex(self.sub(text), r'<li class="navgoal is-current"><a href="/goal/G-002"')
        self.assertEqual(text.count('aria-current="page"'), 1)
        text = self.get("/goal/G-001")
        nav = main_nav(text)
        self.assertRegex(nav, r'<details class="navdone" data-key="nav-done-goals" open>')
        self.assertIn('aria-expanded="true"', nav)
        self.assertRegex(self.sub(text, "navsub navsub--done"), r'<li class="navgoal is-current"><a href="/goal/G-001"')
        self.assertEqual(text.count('aria-current="page"'), 1)

    def test_phone_navs_are_unchanged(self):
        self.goal("G-002", "active")
        self.goal("G-001", "done", closed="2026-10-02T10:00:00+00:00")
        text = self.get("/tasks")
        for nav in (re.search(r'<nav id="more".*?</nav>', text, re.S).group(0),
                    re.search(r'<nav aria-label="Primary tabs".*?</nav>', text, re.S).group(0)):
            self.assertNotIn("navgoal", nav)
            self.assertNotIn("navplus", nav)

    def test_statement_count_does_not_grow_with_goals(self):
        def count():
            n = []
            self.con.set_trace_callback(n.append)
            queries.shell_status(self.con, None, None)
            self.con.set_trace_callback(None)
            return len(n)
        self.goal("G-001", "active", done=1, total=2)
        self.goal("G-002", "done", closed="2026-10-02T10:00:00+00:00")
        base = count()
        for n in range(3, 15):
            self.goal(f"G-0{n:02d}", "active" if n % 2 else "done", done=1, total=3, closed="2026-10-03T10:00:00+00:00")
        self.assertEqual(count(), base)

    def test_page_without_shell_data_has_no_goal_lists(self):
        text = wh.page("Error", "x")
        self.assertNotIn("navsub", text)
        self.assertNotIn("navplus", text)


if __name__ == "__main__":
    unittest.main()
