"""HM-45: links from a story run's goal to its Taskosaur story and children.

The keys come from the engine's `workflow.db` (read-only, web/flowdefs.py) and Taskosaur's base address from config
`tsr_web_url` (e.g. http://localhost:4001/<workspace>/<project>). A task's page is `{tsr_web_url}/tasks/{key}` (owner
rule of 2026-11-15) and opens in a new tab. Without the address the key is plain text. Fixed number of queries per page.
"""
import os
import sqlite3
from urllib.parse import quote

from web import flowdefs
from web.html import el

NEW_TAB, NEW_TAB_REL = "_blank", "noopener noreferrer"


def web_url(con):
    r = con.execute("SELECT value FROM config WHERE key='tsr_web_url'").fetchone()
    v = (r[0] if r else "") or ""
    return v.rstrip("/") if v.startswith(("http://", "https://")) else ""



def stories_by_goal(con):
    """{goal_id: [story keys]} of every story run in workflow.db (one read-only connection), {} without the file."""
    path = flowdefs.db_path(con)
    if not path or not os.path.isfile(path):
        return {}
    try:
        w = sqlite3.connect(f"file:{quote(os.path.abspath(path))}?mode=ro", uri=True, timeout=2)
        try:
            out = {}
            for goal, story in w.execute("SELECT goal_id, story_key FROM run_stories ORDER BY goal_id, position"):
                out.setdefault(goal, []).append(story)
            return out
        finally:
            w.close()
    except sqlite3.Error:
        return {}


def key_el(key, url, cls="mono"):
    """A TSR key: a new-tab link to `{url}/tasks/{key}` when the base address is set, else plain text."""
    if not url:
        return el("span", key, class_=cls)
    href = f"{url}/tasks/{quote(key, safe='')}"
    return el("a", key, href=href, target=NEW_TAB, rel=NEW_TAB_REL, class_=cls, title=f"Open {key} in Taskosaur")
