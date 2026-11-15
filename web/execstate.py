"""HM-47: one execution state per goal and per task, derived in one place and shown the same way on every page.

A state says what is really going on, with a one-line reason:

| State | Goal | Task |
|---|---|---|
| Running | an agent of the goal is live or starting (who) | an agent of the task is live or starting (who) |
| Waiting | open, nobody running, and why (queued for a slot, review/CI, dependency, approval, no agent) | the same, per task |
| Paused | held by the owner (goals.hold = paused, HM-42) or the factory is halted (HM-44) | its goal is paused |
| Stopping | a stop was requested and an agent has not closed yet (with the failure, if any) | the same |
| Stopped | stopped by the owner (goals.hold = stopped) | its goal is stopped |
| Blocked | stuck, with who must act | status blocked, with `waits` |
| Done / Cancelled | as stored | as stored |

Running and Waiting are derived at display time; Paused and Stopped come from stored data (owner decision 2026-11-15).
A state is always rendered as text (badge) plus colour, never colour or an icon alone. Fixed number of queries.
"""
import json

from web.db import has_column
from web.html import el

RUNNING, WAITING, PAUSED, STOPPING, STOPPED, BLOCKED, DONE, CANCELLED = (
    "running", "waiting", "paused", "stopping", "stopped", "blocked", "done", "cancelled")
LABEL = {RUNNING: "Running", WAITING: "Waiting", PAUSED: "Paused", STOPPING: "Stopping", STOPPED: "Stopped",
         BLOCKED: "Blocked", DONE: "Done", CANCELLED: "Cancelled"}
TONE = {RUNNING: "info", WAITING: "warn", PAUSED: "muted", STOPPING: "warn", STOPPED: "muted", BLOCKED: "bad",
        DONE: "ok", CANCELLED: "muted"}
MEANING = (   # the legend, in order
    (RUNNING, "an agent works on it now; the reason names who"),
    (WAITING, "open, but no agent runs now; the reason says what it waits for"),
    (PAUSED, "held by the owner (goal Pause) or the whole factory is halted; nothing of it starts"),
    (STOPPING, "a stop was requested and an agent has not closed yet"),
    (STOPPED, "stopped by the owner; it does not start again"),
    (BLOCKED, "stuck; the label says who must act (red when it is the owner)"),
    (DONE, "finished"),
    (CANCELLED, "closed without finishing"),
)
LIVE = ("live", "starting")
GOAL_OPEN = ("proposed", "planning", "active", "blocked")
TASK_WAIT_REASON = {"todo": "not started", "in_progress": "no agent running", "in_review": "review and CI on its PR"}
GOAL_WAIT_REASON = {"proposed": "waiting for approval", "planning": "being planned"}
WHO_MAX = 3


def _who(agents):
    names = [f"{a['role']} {a['name']}" for a in agents][:WHO_MAX]
    more = len(agents) - len(names)
    return ", ".join(names) + (f" and {more} more" if more > 0 else "")


def _stopping(agents):
    failed = sorted({a["stop_failed_kind"] for a in agents if a["stop_failed_kind"]})
    return "stop requested: " + ", ".join(a["name"] for a in agents) + (f" (last attempt failed: {', '.join(failed)})" if failed else "")


def states(con):
    """{"goals": {goal_id: {state, label, tone, reason}}, "tasks": {task_id: {...}}} for every goal and task. 4 queries."""
    hold_col = has_column(con, "goals", "hold")
    goals = con.execute(f"SELECT id, status, {'hold' if hold_col else 'NULL AS hold'} FROM goals").fetchall()
    tasks = con.execute("SELECT id, goal_id, status, waits, depends_on FROM tasks").fetchall()
    stop_cols = "stop_requested_at, stop_failed_kind" if has_column(con, "agents", "stop_requested_at") else \
        "NULL AS stop_requested_at, NULL AS stop_failed_kind"
    agents = con.execute(f"SELECT name, role, status, goal_id, task_id, {stop_cols} FROM agents "
                         "WHERE status IN ('live','starting','queued')").fetchall()
    halt = con.execute("SELECT value FROM config WHERE key='factory_halt'").fetchone()
    halted = bool(halt) and halt[0] == "1"
    task_goal = {t["id"]: t["goal_id"] for t in tasks}
    by_task, by_goal = {}, {}
    for a in agents:
        gid = a["goal_id"] or task_goal.get(a["task_id"])
        if a["task_id"]:
            by_task.setdefault(a["task_id"], []).append(a)
        if gid:
            by_goal.setdefault(gid, []).append(a)
    goal_hold = {g["id"]: g["hold"] for g in goals}
    done_ids = {t["id"] for t in tasks if t["status"] == "done"}

    def derive(status, hold, mine, waits=None, wait_reason=None):
        if status == "done":
            return DONE, None
        if status == "cancelled":
            return (STOPPED, "by the owner") if hold == "stopped" else (CANCELLED, None)
        if hold == "stopped":
            return STOPPED, "by the owner"
        stopping = [a for a in mine if a["status"] == "live" and a["stop_requested_at"]]
        if stopping:
            return STOPPING, _stopping(stopping)
        if hold == "paused":
            return PAUSED, "by the owner"
        if halted:
            return PAUSED, "the factory is halted (Urgent stop)"
        running = [a for a in mine if a["status"] in LIVE]
        if running:
            return RUNNING, _who(running)
        if status == "blocked":   # the label names who must act: "Blocked: owner" (red), else neutral
            return BLOCKED, (waits if waits and waits != "internal" else "inside the team")
        if any(a["status"] == "queued" for a in mine):
            return WAITING, "queued for a start slot"
        return WAITING, wait_reason

    out = {"goals": {}, "tasks": {}}
    for t in tasks:
        try:
            deps = [d for d in json.loads(t["depends_on"] or "[]") if d not in done_ids]
        except (ValueError, TypeError):
            deps = []
        reason = f"after {', '.join(deps)}" if t["status"] == "todo" and deps else TASK_WAIT_REASON.get(t["status"], "no agent running")
        st, why = derive(t["status"], goal_hold.get(t["goal_id"]), by_task.get(t["id"], []), t["waits"], reason)
        out["tasks"][t["id"]] = _pack(st, why, owner=t["waits"] == "owner")
    blocked_on = {}
    for t in tasks:
        if t["status"] == "blocked" and t["waits"] and t["waits"] != "internal":
            blocked_on.setdefault(t["goal_id"], set()).add(t["waits"])
    for g in goals:
        waits = ", ".join(sorted(blocked_on.get(g["id"], ()))) or None
        st, why = derive(g["status"], g["hold"], by_goal.get(g["id"], []), waits,
                         GOAL_WAIT_REASON.get(g["status"], "no agent running"))
        out["goals"][g["id"]] = _pack(st, why, owner="owner" in blocked_on.get(g["id"], ()))
    return out


def _pack(state, reason, owner=False):
    """Blocked carries whom it waits on in its label ("Blocked: owner") and is red only when the owner must act."""
    if state == BLOCKED:
        return {"state": state, "label": f"{LABEL[state]}: {reason}", "tone": "bad" if owner else "muted", "reason": None}
    return {"state": state, "label": LABEL[state], "tone": TONE[state], "reason": reason}


def badge(st, with_reason=True):
    """The state as a text badge (always a label, never colour alone), the reason after it in muted text."""
    if not st:
        return ""
    b = el("span", st["label"], class_=f"badge badge--{st['tone']}", title=st["reason"] or st["label"],
           data_state=st["state"])
    if with_reason and st["reason"]:
        return el("span", b, " ", el("span", st["reason"], class_="muted"), class_="exec")
    return b


def legend():
    """A small "What the states mean" disclosure for the pages that show states."""
    rows = [el("li", el("span", LABEL[s], class_=f"badge badge--{TONE[s]}"), " ", m) for s, m in MEANING]
    return el("details", el("summary", "What the states mean"), el("ul", rows, class_="lrow-list"), class_="disc exec-legend",
              data_key="exec-legend")
