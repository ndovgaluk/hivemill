"""HM-45: a story run's goal links its Taskosaur story and children (keys from workflow.db) to
{tsr_web_url}/tasks/{key} (owner rule of 2026-11-15), in a new tab; plain text without the address."""
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from harness import FactoryTestCase  # noqa: E402
from test_web_flow_workflow import SCHEMA, WorkflowCase  # noqa: E402
from web import flowdefs as fd  # noqa: E402

LINKS = ('[{"key":"HM-1","workspace":"nick","project":"dev"},{"key":"HM-2","workspace":"nick","project":"dev"},'
         '{"key":"HM-3","workspace":"nick","project":"dev"}]')
BASE = "http://localhost:4001/nick/dev"
STORY = 'href="http://localhost:4001/nick/dev/tasks/HM-1" target="_blank" rel="noopener noreferrer"'


class TsrLinks(WorkflowCase):
    def setUp(self):
        super().setUp()
        self.seed_run("simple", "local")    # G-90, story HM-1, children HM-2 and HM-3
        self.con.execute("INSERT INTO events(ts,actor,entity,entity_id,action,detail) "
                         "VALUES('2026-11-15T10:00:00+11:00','engine','workflow','G-90','story-run-links',?)", (LINKS,))
        self.con.commit()

    def url(self, value):
        self.con.execute("INSERT INTO config(key,value) VALUES('tsr_web_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (value,))
        self.con.commit()

    def page(self, path):
        return self.get(path)[2].decode() if isinstance(self.get(path)[2], bytes) else self.get(path)

    def test_goal_page_header_and_card_link_the_story_and_children_in_a_new_tab(self):
        self.url(BASE)
        text = self.page("/goal/G-90")
        self.assertIn(STORY, text)
        card = text.split('aria-label="Taskosaur"', 1)[1].split("</section>", 1)[0]
        for key in ("HM-2", "HM-3"):
            self.assertIn(f'href="{BASE}/tasks/{key}" target="_blank"', card)
        self.assertIn("fixing · 2 fix rounds", card)

    def test_goals_list_row_shows_the_story_key(self):
        self.url(BASE)
        row = re.search(r'<li class="goalrow">.*?G-90.*?</li>', self.page("/goals"), re.S).group(0)
        self.assertIn(STORY, row)

    def test_without_the_address_the_keys_are_plain_text(self):
        text = self.page("/goal/G-90")
        self.assertIn('<span class="mono tsr-key">HM-1</span>', text)
        self.assertNotIn("/tasks/HM-1", text)
        self.assertIn("Set tsr_web_url on the Settings page", text)

    def test_a_goal_that_is_no_story_run_shows_no_key_and_no_card(self):
        self.seed()   # G-80, an old-workflow goal
        self.url(BASE)
        text = self.page("/goal/G-80")
        self.assertNotIn('aria-label="Taskosaur"', text)
        self.assertNotIn("tsr-key", text)

    def test_the_link_needs_no_recorded_place(self):
        self.url(BASE)
        self.con.execute("DELETE FROM events WHERE action='story-run-links'")
        self.con.commit()
        self.assertIn(STORY, self.page("/goal/G-90"))

class Config(FactoryTestCase):
    def test_the_address_must_be_http_or_https(self):
        for bad in ("javascript:alert(1)", "ftp://x", 'http://x"onmouseover=1'):
            with self.subTest(bad):
                p = self.env.run("config", "tsr_web_url", bad)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertIn("tsr_web_url must be an http:// or https:// address", p.stderr)
        self.assertEqual(self.env.run("config", "tsr_web_url", BASE + "/").returncode, 0)
        self.assertEqual(self.env.sql("SELECT value FROM config WHERE key='tsr_web_url'")[0]["value"], BASE)


if __name__ == "__main__":
    unittest.main()
