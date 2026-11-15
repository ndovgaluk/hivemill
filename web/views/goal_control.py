"""HM-42: the owner's goal controls. The goal page links each action here (GET /goal-control?goal=G-001&action=pause),
which says what the action does to the goal and holds the one form that confirms it (the goal page itself stays without
forms and form token).
POST /goal-control (web/server.py _goal_control_post) runs `factory goal pause|resume|stop G --reason`."""
import re

from web.html import el
from web.views import settings as settings_view

TITLE = "Goal control"
FORMS = True
NAV = "/goals"
PATH = "/goal-control"
ACTIONS = ("pause", "resume", "stop")
CONFIRM = ACTIONS                 # every action is confirmed on this page
GOAL_RE = re.compile(r"^G-\d{1,6}$")
REASON_MAX = 200
LABEL = {"pause": "Pause", "resume": "Resume", "stop": "Stop"}
RUNNING = ("queued", "starting", "live")


def run(factory_home, goal, action, reason, env=None):
    """`bin/factory goal <action> <goal> --reason ...` (the CLI checks the role and does the work); (ok, last line)."""
    return settings_view._run_factory(factory_home, ["goal", action, goal, "--reason", reason], env, f"factory goal {action}")


def form(ctx, goal, action, *fields, label=None, cls="set-btn"):
    return el("form", el("input", type="hidden", name="token", value=ctx.form_token or ""),
              el("input", type="hidden", name="goal", value=goal), el("input", type="hidden", name="action", value=action),
              *fields, el("button", label or LABEL[action], type="submit", class_=cls), method="post", action=PATH,
              class_="set-form goal-ctl-form")


def data(ctx):
    goal, action = ctx.query.get("goal", ""), ctx.query.get("action", "")
    if not GOAL_RE.match(goal) or action not in CONFIRM:
        return {"ok": False}
    g = ctx.db.execute("SELECT id, title, status FROM goals WHERE id=?", (goal,)).fetchone()
    if not g:
        return {"ok": False}
    ph = ",".join("?" * len(RUNNING))
    agents = [r["name"] for r in ctx.db.execute(
        f"SELECT name FROM agents WHERE status IN ({ph}) AND (goal_id=? OR task_id IN (SELECT id FROM tasks WHERE goal_id=?)) "
        "ORDER BY name", (*RUNNING, goal, goal))]
    prs = [dict(r) for r in ctx.db.execute("SELECT id, pr_url FROM tasks WHERE goal_id=? AND pr_url IS NOT NULL "
                                           "AND status NOT IN ('done','cancelled') ORDER BY id", (goal,))]
    return {"ok": True, "goal": dict(g), "action": action, "agents": agents, "prs": prs, "editable": bool(ctx.loopback)}


WHAT = {"pause": ("Pause", "The goal is held: the factory starts none of its agents until Resume.",
                   "Pull requests, branches and worktrees stay; the goal stays open."),
        "resume": ("Resume", "The hold is cleared: the tick and the goal's lead start fresh agents from the task states.",
                   "No old agent session is revived.")}


def render(ctx, d):
    if not d["ok"]:
        return el("p", "Nothing to confirm: open a goal and use its controls.", class_="empty")
    g, action = d["goal"], d["action"]
    if action in WHAT:
        verb, line1, line2 = WHAT[action]
        out = [el("p", f"{verb} goal {g['id']}: {g['title']}", class_="halt-state"),
               el("ul", [el("li", line1)] + ([el("li", f"{len(d['agents'])} agent(s) of the goal are stopped now"
                                                       + (f": {', '.join(d['agents'])}" if d["agents"] else "") + ".")]
                                             if action == "pause" else []) + [el("li", line2)], class_="lrow-list")]
        out.append(form(ctx, g["id"], action, el("input", type="text", name="reason", maxlength=str(REASON_MAX),
                                                  placeholder="Reason (optional)", aria_label="Reason", class_="set-input"),
                        label=f"{verb} the goal") if d["editable"]
                   else el("code", f"factory goal {action} {g['id']} --reason \"...\"", class_="set-cmd"))
        return el("div", *out, class_="settings halt-page")
    out = [el("p", f"Stop goal {g['id']}: {g['title']}", class_="halt-state"),
           el("ul", [el("li", f"{len(d['agents'])} agent(s) of the goal are stopped now"
                              + (f": {', '.join(d['agents'])}" if d["agents"] else "") + "."),
                     el("li", "The goal is cancelled and starts nobody again; a stopped goal is not resumed."),
                     el("li", f"{len(d['prs'])} open pull request(s) are left as they are"
                              + (f": {', '.join(p['id'] for p in d['prs'])}" if d["prs"] else "") + "."),
                     el("li", "Nothing is deleted: tasks, branches and worktrees stay.")], class_="lrow-list")]
    out.append(form(ctx, g["id"], "stop", el("input", type="text", name="reason", maxlength=str(REASON_MAX),
                                             placeholder="Reason (optional)", aria_label="Reason", class_="set-input"),
                    label="Stop the goal", cls="set-btn halt-go") if d["editable"]
               else el("code", f"factory goal stop {g['id']} --reason \"...\"", class_="set-cmd"))
    return el("div", *out, class_="settings halt-page")
