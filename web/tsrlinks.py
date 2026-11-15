"""HM-45: links from a story run's goal to its Taskosaur story and children.

The keys come from the engine's `workflow.db` (read-only, web/flowdefs.py) and Taskosaur's base address from config
`tsr_web_url` (e.g. http://localhost:4001/<workspace>/<project>). A task's page is `{tsr_web_url}/tasks/{key}` (owner
rule of 2026-11-15) and opens in a new tab. Without the address the key is plain text. Fixed number of queries per page.
"""
import os
import sqlite3
from urllib.parse import quote

from web import flowdefs
from web.html import Safe, el

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


# HM-45 follow-up (owner, 2026-11-16): a key is a grey chip with a copy icon; theme.js copies `data-copy` on click and
# shows the check mark for a moment. Without JavaScript the button does nothing and the link still works.
_COPY_SVG = ('<svg class="i-copy" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" '
             'stroke-linejoin="round" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/>'
             '<path d="M10.5 3.5v-.5A1.5 1.5 0 0 0 9 1.5H3A1.5 1.5 0 0 0 1.5 3v6A1.5 1.5 0 0 0 3 10.5h.5"/></svg>'
             '<svg class="i-ok" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.75" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5 6.5 12 13 4.5"/></svg>')


def key_el(key, url):
    """A TSR key as a chip: a new-tab link to `{url}/tasks/{key}` when the base address is set (else plain text), then a
    button that copies the key."""
    if url:
        label = el("a", key, href=f"{url}/tasks/{quote(key, safe='')}", target=NEW_TAB, rel=NEW_TAB_REL,
                   class_="mono tsr-key", title=f"Open {key} in Taskosaur")
    else:
        label = el("span", key, class_="mono tsr-key")
    copy = el("button", Safe(_COPY_SVG), type="button", class_="tsr-copy", data_copy=key,
              aria_label=f"Copy {key}", title=f"Copy {key}")
    return el("span", label, copy, class_="tsr-chip")
