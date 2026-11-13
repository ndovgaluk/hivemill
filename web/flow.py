"""Flow debugger data (DVDG-553): one goal or one task as the JSON the React flow app renders.

Served at /api/flow/goal/<id>.json and /api/flow/task/<id>.json (web/server.py). Read-only. The shape is the
"Shared contract" of story DVDG-551: scope header, totals, nodes, edges, lanes, events, findings, phases. Unknown is
None (JSON null) with a `*_note` reason where it matters, never 0 or a guess. Instruction text (message bodies,
verdict summaries, the task's spec and acceptance, an agent's end summary) is selected from the DB only when
`show_text` (web/server.show_text_allowed); otherwise those columns are never read.
"""
from web.html import is_pr_url
from web import queries as q
from web.html import md


class Scope:
    GOAL, TASK = "goal", "task"
    ALL = (GOAL, TASK)


class Node:
    BOSS, DIRECTOR, LEAD, SYSTEM = "boss", "director", "lead", "system"
    PM, CODERS, REVIEWER, QA, JUDGE, MAIN = "pm", "coders", "reviewer", "qa", "judge", "main"
    WAIT = "wait"   # no role: live while the scope is open and no agent of it runs (HM-13)
    GATE = "gate"   # HM-17: not a node any more, the id of the group (frame) holding REVIEWER and QA


NODES = ((Node.BOSS, "Boss"), (Node.DIRECTOR, "Director"), (Node.LEAD, "Lead"), (Node.SYSTEM, "System"), (Node.PM, "PM"),
         (Node.CODERS, "Coders"), (Node.REVIEWER, "Reviewer"), (Node.QA, "QA"), (Node.JUDGE, "Judge"), (Node.MAIN, "Merged"),
         (Node.WAIT, "Waiting"))
GATE_NODES = (Node.REVIEWER, Node.QA)
# HM-17: every actor has its own box; boxes that act as one step sit in a group (drawn as a dashed frame)
GROUPS = ((Node.GATE, "Review gate", GATE_NODES),)
WORKERS = (Node.PM, Node.CODERS, *GATE_NODES, Node.JUDGE)


class Edge:
    BD, DL, SL, BUS, PC, CG, GJ, JM, RW = "bd", "dl", "sl", "bus", "pc", "cg", "gj", "jm", "rw"


# id -> (from node, to nodes, label); dir 1 = from → to, -1 = back
# labels are short: they sit in the 68px gap between two boxes
EDGES = ((Edge.BD, Node.BOSS, (Node.DIRECTOR,), "requests"),
         (Edge.DL, Node.DIRECTOR, (Node.LEAD,), "brief"),
         (Edge.SL, Node.SYSTEM, (Node.LEAD,), "kickoff"),
         (Edge.BUS, Node.LEAD, WORKERS, "brief ↓ report ↑"),
         (Edge.PC, Node.PM, (Node.CODERS,), "queued"),
         (Edge.CG, Node.CODERS, GATE_NODES, "review"),
         (Edge.GJ, Node.GATE, (Node.JUDGE,), "verdict"),      # from the group: the frame's edge, either role
         (Edge.JM, Node.JUDGE, (Node.MAIN,), "merge"),
         (Edge.RW, Node.GATE, (Node.CODERS,), "rework"))
_EDGE_OF = {(Node.BOSS, Node.DIRECTOR): (Edge.BD, 1), (Node.DIRECTOR, Node.BOSS): (Edge.BD, -1),
            (Node.DIRECTOR, Node.LEAD): (Edge.DL, 1), (Node.LEAD, Node.DIRECTOR): (Edge.DL, -1),
            (Node.SYSTEM, Node.LEAD): (Edge.SL, 1),
            (Node.PM, Node.CODERS): (Edge.PC, 1), (Node.CODERS, Node.GATE): (Edge.CG, 1),
            (Node.JUDGE, Node.MAIN): (Edge.JM, 1),
            **{(Node.CODERS, g): (Edge.CG, 1) for g in GATE_NODES},
            **{(g, Node.JUDGE): (Edge.GJ, 1) for g in GATE_NODES},
            **{(g, Node.CODERS): (Edge.RW, 1) for g in GATE_NODES},
            **{(src, w): (Edge.BUS, 1) for w in WORKERS for src in (Node.LEAD, Node.SYSTEM)},
            **{(w, Node.LEAD): (Edge.BUS, -1) for w in WORKERS}}


class Lane:
    BOSS, DIRECTOR, SYSTEM, LEAD, PM = "boss", "director", "system", "lead", "pm"
    CODERS, REVIEWER, QA, JUDGE = "coders", "reviewer", "qa", "judge"
    WAIT = "wait"   # no role: the stretches in which no agent of the scope ran (HM-18)


LANES = ((Lane.BOSS, Node.BOSS, "Boss"), (Lane.DIRECTOR, Node.DIRECTOR, "Director"), (Lane.SYSTEM, Node.SYSTEM, "System"),
         (Lane.LEAD, Node.LEAD, "Lead"), (Lane.PM, Node.PM, "PM"), (Lane.CODERS, Node.CODERS, "Coders"),
         (Lane.REVIEWER, Node.REVIEWER, "Reviewer"), (Lane.QA, Node.QA, "QA"), (Lane.JUDGE, Node.JUDGE, "Judge"),
         (Lane.WAIT, Node.WAIT, "Waiting"))
_LANE_NODE = {lane: node for lane, node, _ in LANES}
_NODE_LANE = {Node.BOSS: Lane.BOSS, Node.DIRECTOR: Lane.DIRECTOR, Node.SYSTEM: Lane.SYSTEM, Node.LEAD: Lane.LEAD,
              Node.PM: Lane.PM, Node.CODERS: Lane.CODERS, Node.REVIEWER: Lane.REVIEWER, Node.QA: Lane.QA,
              Node.JUDGE: Lane.JUDGE, Node.MAIN: Lane.JUDGE, Node.WAIT: Lane.WAIT}


class Role:
    OWNER, BOSS, DIRECTOR, LEAD, PM = "owner", "boss", "director", "lead", "pm"
    CODER, REVIEWER, QA, JUDGE = "coder", "reviewer", "qa", "judge"


# the owner talks to the boss: both sit in the HQ box at the top left
_ROLE_LANE = {Role.OWNER: Lane.BOSS, Role.BOSS: Lane.BOSS, Role.DIRECTOR: Lane.DIRECTOR, Role.LEAD: Lane.LEAD,
              Role.PM: Lane.PM, Role.CODER: Lane.CODERS, Role.REVIEWER: Lane.REVIEWER, Role.QA: Lane.QA,
              Role.JUDGE: Lane.JUDGE}
GATE_ROLES = (Role.REVIEWER, Role.QA)
VERDICT_NODE = {Role.REVIEWER: Node.REVIEWER, Role.QA: Node.QA, Role.JUDGE: Node.JUDGE}   # who a verdict comes from
SYSTEM_SENDERS = ("factory", "tick")   # the CLI itself (kickoffs, notices); same list as queries._SYSTEM_SENDERS


class State:
    DONE, LIVE, FAIL, IDLE, PENDING = "done", "live", "fail", "idle", "pending"


class Severity:
    OK, WARN, BAD = "ok", "warn", "bad"
    ORDER = (OK, WARN, BAD)


class SpanKind:
    WORK, WAIT, FAIL = "work", "wait", "fail"


class EventKind:
    MSG, STATUS, VERDICT = "msg", "status", "verdict"


class FindingTarget:
    NODE, EDGE, EVENT = "node", "edge", "event"


class Key:
    """Event keys: the factory's own message key style (`M62`, printed by the CLI), extended to verdicts and events."""
    MESSAGE, VERDICT, EVENT, SPEC = "M", "V", "E", "S-"


class Table:
    MESSAGES, VERDICTS, EVENTS, TASKS = "messages", "verdicts", "events", "tasks"


class Action:
    SPAWN, DONE, AUTO_START, PR_CREATE, MERGED = "spawn", "done", "task-auto-start", "pr-create", "merged"
    REVIEWER_PASS, REVIEWER_FAIL, QA_PASS, QA_FAIL = "reviewer-pass", "reviewer-fail", "qa-pass", "qa-fail"
    REAPED, STOPPED, LOST = "reaped", "stopped", "lost"


TIMELINE_ACTIONS = (Action.SPAWN, Action.DONE, Action.AUTO_START, Action.PR_CREATE, Action.REVIEWER_PASS,
                    Action.REVIEWER_FAIL, Action.QA_PASS, Action.QA_FAIL, Action.MERGED)
VERDICT_ACTIONS = (Action.REVIEWER_PASS, Action.REVIEWER_FAIL, Action.QA_PASS, Action.QA_FAIL)
# event details that are facts (a sha, a PR url, "spawn pm-t-0001"), never instruction text
FACT_DETAIL_ACTIONS = (Action.AUTO_START, Action.PR_CREATE, Action.MERGED, *VERDICT_ACTIONS)
SESSION_END_ACTIONS = (Action.DONE, Action.REAPED, Action.STOPPED, Action.LOST)
INSTRUCTION_KINDS = ("request", "decision", "escalation")
WARN_KINDS = ("escalation", "alert")
REJECT_VERDICTS = ("fail", "reject")
MERGE_VERDICT = "merge"
LIVE_STATUSES = ("live", "starting")
TERMINAL_TASK = ("done", "cancelled")
TERMINAL_GOAL = ("done", "cancelled", "abandoned")
IN_REVIEW = "in_review"
WAIT_WARN_S = 10 * 60     # a handoff wait at or over this is drawn as a warning (DVDG-560 default)
WAIT_BAD_S = 60 * 60      # … and at or over this as bad
TITLE_CHARS = 140
COST_NOTE = "token usage not loaded"   # replaced by web/flowcost.fill (DVDG-555) when the server has a token index
NOTE_RUNNING = "running"
NOTE_NO_END = "end not recorded"
NOTE_QUEUED = "queued before coding"
NOTE_NO_CODER_START = "left the queue without a recorded coder start"
# what the Waiting box says nobody is running for (HM-13); the first two are followed by the task ids
WAIT_REVIEW = "PR checks, then review"   # a PR is open and no reviewer or QA has started on it: CI runs first
WAIT_QUEUE = "next task not started"
WAIT_UNKNOWN = "no agent running"
WAIT_LINK_LABEL = "PR"
WAIT_ROW = "no agent running"   # the one row of the Waiting lane


def _sev_max(*sevs):
    return max((s for s in sevs if s), key=Severity.ORDER.index, default=Severity.OK)


def _wait_sev(s):
    return Severity.OK if s is None else Severity.BAD if s >= WAIT_BAD_S else Severity.WARN if s >= WAIT_WARN_S else Severity.OK


def build(con, scope, oid, now=None, show_text=False):
    """The flow dict for goal or task `oid`, or None when it does not exist (or the scope is unknown)."""
    if scope not in Scope.ALL:
        return None
    now_d = q._now(now)
    now_e = now_d.timestamp()
    if scope == Scope.GOAL:
        head = con.execute("SELECT id, title, status, created FROM goals WHERE id=?", (oid,)).fetchone()
        if head is None:
            return None
        tasks = q._dicts(con.execute("SELECT rowid, id, goal_id, status, created, pr_url FROM tasks WHERE goal_id=? ORDER BY created, id",
                                     (oid,)))
        agents = q._dicts(con.execute(
            "SELECT name, role, status, task_id, goal_id, session_id, started, ended FROM agents WHERE goal_id=? "
            "OR task_id IN (SELECT id FROM tasks WHERE goal_id=?) ORDER BY started, name", (oid, oid)))
        start = head["created"]
        goal_id = oid
    else:
        head = con.execute("SELECT rowid, id, goal_id, title, status, created, pr_url FROM tasks WHERE id=?", (oid,)).fetchone()
        if head is None:
            return None
        tasks = [dict(head)]
        goal_id = head["goal_id"]
        lc = q.task_lifecycle(con, oid, now)
        start = lc["total"]["start"] or head["created"]
        add = con.execute("SELECT actor FROM events WHERE entity='task' AND entity_id=? AND action='add' ORDER BY id LIMIT 1",
                          (oid,)).fetchone()
        agents = q._dicts(con.execute(
            "SELECT name, role, status, task_id, goal_id, session_id, started, ended FROM agents WHERE task_id=? "
            "OR (role=? AND goal_id=?) OR name=? ORDER BY started, name",
            (oid, Role.LEAD, goal_id, add["actor"] if add else None)))
    start_e = q._epoch(start)
    roles = {r["name"]: r["role"] for r in con.execute("SELECT name, role FROM agents")}
    task_ids = [t["id"] for t in tasks]
    names = [a["name"] for a in agents]

    def off(e):
        """Seconds from the scope's start; None when either end is unknown (an unparsable `created`)."""
        return round(e - start_e) if e is not None and start_e is not None else None

    def rel(ts):
        return off(q._epoch(ts))

    def lane_of(name):
        if name in SYSTEM_SENDERS:
            return Lane.SYSTEM
        return _ROLE_LANE.get(roles.get(name, name))

    def node_of(name):
        lane = lane_of(name)
        return _LANE_NODE.get(lane) if lane else None

    # ── sessions per agent: spawn → done/reaped/stopped/lost events (every session, not only the latest row) ──
    sess = {n: [] for n in names}
    open_s = {}
    for r in q._in(con, "SELECT ts, entity_id, action FROM events WHERE entity='agent' AND action IN (%s) AND entity_id IN ({in}) "
                        "ORDER BY id" % ",".join("?" * (1 + len(SESSION_END_ACTIONS))), names, Action.SPAWN, *SESSION_END_ACTIONS):
        n, e = r["entity_id"], q._epoch(r["ts"])
        if e is None:
            continue
        if r["action"] == Action.SPAWN:
            if n in open_s:   # started again with no end event in between: that session's end is unknown
                sess[n].append([open_s.pop(n), None, NOTE_NO_END])
            open_s[n] = e
        elif n in open_s:
            sess[n].append([open_s.pop(n), e, None])
    agent_by = {a["name"]: a for a in agents}
    for n, s0 in open_s.items():
        a = agent_by[n]
        if a["status"] in LIVE_STATUSES:
            sess[n].append([s0, now_e, NOTE_RUNNING])
        else:
            end = q._epoch(a["ended"])
            sess[n].append([s0, end if end is not None and end >= s0 else None, None if end is not None and end >= s0 else NOTE_NO_END])
    for a in agents:   # no spawn event at all (older rows, seeded data): the row's own start and end
        if sess[a["name"]]:
            continue
        s0, e = q._epoch(a["started"]), q._epoch(a["ended"])
        if s0 is None:
            continue
        if a["status"] in LIVE_STATUSES:
            sess[a["name"]].append([s0, now_e, NOTE_RUNNING])
        else:
            sess[a["name"]].append([s0, e if e is not None and e >= s0 else None, None if e is not None and e >= s0 else NOTE_NO_END])

    # ── verdicts (needed for failing spans and events) ──
    vcols = "id, task_id, role, verdict, head_sha, author, created" + (", summary" if show_text else "")
    verdicts = q._dicts(q._in(con, f"SELECT {vcols} FROM verdicts WHERE task_id IN ({{in}}) ORDER BY id", task_ids))
    fails_by = {}
    for v in verdicts:
        if v["verdict"] in REJECT_VERDICTS and v["author"]:
            fails_by.setdefault(v["author"], []).append(q._epoch(v["created"]))

    def work_of(n):
        spans = sess.get(n) or []
        if not spans or any(s[1] is None for s in spans):
            return None
        return round(sum(s[1] - s[0] for s in spans))

    # ── lanes ──
    coder_of = {}
    for a in agents:
        if a["role"] == Role.CODER and a["task_id"]:
            coder_of[a["task_id"]] = a["name"]   # the latest coder (rows are ordered by start)
    rows_by_lane = {lane: [] for lane, _, _ in LANES}
    row_names = set()
    for a in agents:
        lane = _ROLE_LANE.get(a["role"])
        if lane is None:
            continue
        spans = []
        for s0, s1, note in sess[a["name"]]:
            failed = any(f is not None and s0 <= f <= (s1 if s1 is not None else now_e) for f in fails_by.get(a["name"], ()))
            spans.append({"start_s": off(s0), "end_s": off(s1),
                          "kind": SpanKind.FAIL if failed else SpanKind.WORK, "note": note})
        rows_by_lane[lane].append({"name": a["name"], "task_id": a["task_id"], "spans": spans})
        row_names.add(a["name"])
    first_coder = {}   # task id -> (first coder session start, that coder's name)
    for a in agents:
        if a["role"] == Role.CODER and a["task_id"]:
            starts = [s[0] for s in sess[a["name"]]]
            if starts and (a["task_id"] not in first_coder or min(starts) < first_coder[a["task_id"]][0]):
                first_coder[a["task_id"]] = (min(starts), a["name"])
    queued = {}
    pc_waits = []      # per task, for edges[].waits (findings, inspector)
    for t in tasks:   # queued before coding: task created → its first coder start (open: until now)
        c0, (f, name) = q._epoch(t["created"]), first_coder.get(t["id"], (None, coder_of.get(t["id"])))
        if c0 is None:
            continue
        if f is None and (t["status"] in TERMINAL_TASK or t["status"] == IN_REVIEW):
            queued[t["id"]] = None   # left the queue without a recorded coder start: unknown
            pc_waits.append({"task_id": t["id"], "wait_s": None, "start_s": off(c0), "end_s": None, "open": False,
                             "note": NOTE_NO_CODER_START})
            continue
        end = f if f is not None else now_e
        if end < c0:
            continue
        queued[t["id"]] = round(end - c0)
        pc_waits.append({"task_id": t["id"], "wait_s": queued[t["id"]], "start_s": off(c0), "end_s": off(end),
                         "open": f is None, "note": None})
        span = {"start_s": off(c0), "end_s": off(end), "kind": SpanKind.WAIT, "note": NOTE_QUEUED}
        row = next((r for r in rows_by_lane[Lane.CODERS] if r["name"] == name), None) if name else None
        if row is None:
            row = {"name": t["id"], "task_id": t["id"], "spans": []}
            rows_by_lane[Lane.CODERS].append(row)
        row["spans"].insert(0, span)
    lanes = [{"id": lane, "node": node, "label": label, "rows": rows_by_lane[lane]} for lane, node, label in LANES]

    # ── events ──
    events = []

    def add_event(key, ref, ts, task_id, frm, to, fn, tn, kind, title, severity=Severity.OK, instruction=False, body=None,
                  edge=None):
        if edge is None:
            edge, d = _EDGE_OF.get((fn, tn), (None, None))
        else:
            edge, d = edge
        lane = lane_of(frm) or _NODE_LANE.get(fn)
        events.append({"id": key, "key": key, "ref": ref, "task_id": task_id, "goal_id": goal_id, "t_s": rel(ts), "ts": ts,
                       "lane": lane, "row": frm if frm in row_names else None, "edge": edge, "dir": d, "from": frm, "to": to,
                       "from_node": fn, "to_node": tn, "kind": kind, "severity": severity, "title": (title or "")[:TITLE_CHARS],
                       "is_instruction": instruction, "body_html": md(body) if show_text and body else None,
                       "tokens": None, "cost": None, "cost_note": COST_NOTE, "cost_exact": False})

    mcols = "id, sender, recipient, kind, subject, task_id, created" + (", body" if show_text else "")
    if scope == Scope.GOAL:
        msgs = con.execute(f"SELECT {mcols} FROM messages WHERE goal_id=? OR task_id IN (SELECT id FROM tasks WHERE goal_id=?) "
                           "ORDER BY id", (oid, oid))
    else:
        msgs = con.execute(f"SELECT {mcols} FROM messages WHERE task_id=? ORDER BY id", (oid,))
    n_msgs = 0
    for m in msgs:
        n_msgs += 1
        add_event(f"{Key.MESSAGE}{m['id']}", {"table": Table.MESSAGES, "rowid": m["id"]}, m["created"], m["task_id"],
                  m["sender"], m["recipient"], node_of(m["sender"]), node_of(m["recipient"]), EventKind.MSG,
                  f"{m['kind']}: {m['subject']}", Severity.WARN if m["kind"] in WARN_KINDS else Severity.OK,
                  m["kind"] in INSTRUCTION_KINDS, m["body"] if show_text else None)
    rejections = 0
    for v in verdicts:
        fn = VERDICT_NODE.get(v["role"])
        sha = f" @{v['head_sha'][:8]}" if v["head_sha"] else ""
        title = f"{v['role']} {v['verdict'].upper()}{sha}"
        ref = {"table": Table.VERDICTS, "rowid": v["id"]}
        body = v["summary"] if show_text else None
        if v["verdict"] in REJECT_VERDICTS:
            rejections += 1
            coder = coder_of.get(v["task_id"])
            add_event(f"{Key.VERDICT}{v['id']}", ref, v["created"], v["task_id"], v["author"] or v["role"], coder or v["task_id"],
                      fn, Node.CODERS, EventKind.VERDICT, title, Severity.BAD, True, body,
                      edge=(Edge.RW, 1) if fn in GATE_NODES else (None, None))
        else:
            tn = Node.MAIN if v["verdict"] == MERGE_VERDICT else Node.JUDGE
            add_event(f"{Key.VERDICT}{v['id']}", ref, v["created"], v["task_id"], v["author"] or v["role"], tn, fn, tn,
                      EventKind.VERDICT, title, Severity.OK, False, body)
    tcols = "rowid, id, created" + (", spec, acceptance" if show_text else "")
    for t in q._in(con, f"SELECT {tcols} FROM tasks WHERE id IN ({{in}})", task_ids):
        adder = con.execute("SELECT actor FROM events WHERE entity='task' AND entity_id=? AND action='add' ORDER BY id LIMIT 1",
                            (t["id"],)).fetchone()
        frm = adder["actor"] if adder else None
        body = f"{t['spec'] or ''}\n\n## Acceptance\n\n{t['acceptance'] or ''}" if show_text and (t["spec"] or t["acceptance"]) else None
        add_event(f"{Key.SPEC}{t['id']}", {"table": Table.TASKS, "rowid": t["rowid"]}, t["created"], t["id"], frm,
                  coder_of.get(t["id"], t["id"]), Node.PM, Node.CODERS, EventKind.STATUS, f"{t['id']} spec and acceptance",
                  Severity.OK, True, body, edge=(Edge.PC, 1))
    acts = ",".join("?" * len(TIMELINE_ACTIONS))
    facts = ",".join("?" * len(FACT_DETAIL_ACTIONS))
    detail = (f"CASE WHEN action IN ({facts}) OR (entity='agent' AND action=?) THEN detail END" if show_text
              else f"CASE WHEN action IN ({facts}) THEN detail END")
    dpre = (*FACT_DETAIL_ACTIONS, Action.DONE) if show_text else FACT_DETAIL_ACTIONS
    erows = q._in(con, f"SELECT id, ts, actor, entity, entity_id, action, {detail} detail FROM events WHERE entity='task' "
                       f"AND action IN ({acts}) AND entity_id IN ({{in}})", task_ids, *dpre, *TIMELINE_ACTIONS)
    erows += q._in(con, f"SELECT id, ts, actor, entity, entity_id, action, {detail} detail FROM events WHERE entity='agent' "
                        f"AND action IN ({acts}) AND entity_id IN ({{in}})", names, *dpre, *TIMELINE_ACTIONS)
    for e in sorted(erows, key=lambda r: r["id"]):
        key, ref = f"{Key.EVENT}{e['id']}", {"table": Table.EVENTS, "rowid": e["id"]}
        act, who, det = e["action"], e["entity_id"], e["detail"] or ""
        tid = who if e["entity"] == "task" else agent_by.get(who, {}).get("task_id")
        if e["entity"] == "agent" and act == Action.SPAWN:
            add_event(key, ref, e["ts"], tid, e["actor"], who, node_of(e["actor"]) or Node.SYSTEM, node_of(who), EventKind.STATUS,
                      f"{who} started")
        elif e["entity"] == "agent" and act == Action.DONE:
            add_event(key, ref, e["ts"], tid, who, None, node_of(who), Node.LEAD if node_of(who) in WORKERS else None,
                      EventKind.STATUS, f"{who} ended", body=det if show_text else None)
        elif act == Action.AUTO_START:
            target = det.split()[-1] if det.split() else None
            add_event(key, ref, e["ts"], tid, e["actor"], target, node_of(e["actor"]) or Node.SYSTEM, node_of(target),
                      EventKind.STATUS, f"{e['actor']}: {det}" if det else f"{e['actor']}: {act}")
        elif act == Action.PR_CREATE:
            add_event(key, ref, e["ts"], tid, e["actor"], None, Node.CODERS, Node.GATE, EventKind.STATUS, f"{who}: PR opened")
        elif act == Action.MERGED:
            add_event(key, ref, e["ts"], tid, e["actor"], None, Node.JUDGE, Node.MAIN, EventKind.STATUS, f"{who} merged {det}".strip())
        elif act in VERDICT_ACTIONS:   # the verdict row is the arrow; this log line is a marker on the timeline only
            role_node = Node.QA if act in (Action.QA_PASS, Action.QA_FAIL) else Node.REVIEWER
            add_event(key, ref, e["ts"], tid, e["actor"], None, role_node, None, EventKind.STATUS, f"{who}: {act} {det}".strip(),
                      Severity.BAD if act in (Action.REVIEWER_FAIL, Action.QA_FAIL) else Severity.OK, edge=(None, None))
        else:   # task done
            add_event(key, ref, e["ts"], tid, e["actor"], None, node_of(e["actor"]), None, EventKind.STATUS, f"{who} {act}")
    events.sort(key=lambda ev: (q._epoch(ev["ts"]) or 0, ev["ref"]["table"], ev["ref"]["rowid"]))

    # ── edges ──
    merged = {r["entity_id"] for r in q._in(con, "SELECT entity_id FROM events WHERE entity='task' AND action=? "
                                                 "AND entity_id IN ({in})", task_ids, Action.MERGED)}
    judged = any(q._judge_reached(con, t) for t in task_ids)
    cg_waits = []
    for t in tasks:   # PR opened (or in_review) → the first reviewer/QA start after it, per review round
        rounds = [q._epoch(r["ts"]) for r in con.execute(
            "SELECT ts FROM events WHERE entity='task' AND entity_id=? AND action='update' AND (detail LIKE ? OR detail LIKE ?) "
            "ORDER BY id", (t["id"], f"%status={IN_REVIEW}%", "%pr=%"))]
        gate_starts = sorted(s[0] for a in agents if a["task_id"] == t["id"] and a["role"] in GATE_ROLES for s in sess[a["name"]])
        gate_verdicts = [q._epoch(v["created"]) for v in verdicts if v["task_id"] == t["id"] and v["role"] in GATE_ROLES]
        known = [r for r in rounds if r is not None]
        for r0 in known:
            s = next((g for g in gate_starts if g >= r0), None)
            if s is not None:
                cg_waits.append({"task_id": t["id"], "wait_s": round(s - r0), "start_s": off(r0), "end_s": off(s),
                                 "open": False, "note": None})
            elif (t["status"] == IN_REVIEW and t["id"] not in merged and r0 == max(known)
                  and not any(v is not None and v >= r0 for v in gate_verdicts)):
                # still waiting: no reviewer/QA started or answered since
                cg_waits.append({"task_id": t["id"], "wait_s": round(now_e - r0), "start_s": off(r0), "end_s": off(now_e),
                                 "open": True, "note": None})
            # else: a verdict came without a recorded session start: this round's wait is unknown
    per_edge = {Edge.PC: pc_waits, Edge.CG: cg_waits}
    waits = {eid: max((w["wait_s"] for w in ws if w["wait_s"] is not None), default=None) for eid, ws in per_edge.items()}
    edges = []
    for eid, frm, to, label in EDGES:
        on = [ev for ev in events if ev["edge"] == eid]
        wait = waits.get(eid)
        pending = (eid == Edge.GJ and not judged) or (eid == Edge.JM and not merged)
        edges.append({"id": eid, "from": frm, "to": list(to), "label": label, "wait_s": wait,
                      "severity": _sev_max(_wait_sev(wait), *(ev["severity"] for ev in on if ev["kind"] != EventKind.STATUS)),
                      "pending": pending, "counts": {"forward": sum(ev["dir"] == 1 for ev in on),
                                                     "back": sum(ev["dir"] == -1 for ev in on)},
                      "waits": per_edge.get(eid, [])})

    # ── nodes ──
    # HM-17: a review box fails while its own role's last verdict on some unmerged task rejects
    last_by = {g: {} for g in GATE_NODES}
    for v in verdicts:
        if v["role"] in GATE_ROLES:
            last_by[VERDICT_NODE[v["role"]]][v["task_id"]] = v["verdict"]
    open_fail = {g: any(vd in REJECT_VERDICTS and tid not in merged for tid, vd in last.items()) for g, last in last_by.items()}
    terminal = head["status"] in (TERMINAL_GOAL if scope == Scope.GOAL else TERMINAL_TASK)
    # the Waiting box (HM-13): the scope is open, it had agents, and none of them runs now
    waiting = not terminal and bool(agents) and not any(a["status"] in LIVE_STATUSES for a in agents)
    wait_s = wait_note = wait_total = None
    wait_links = []
    # all the time since the first session in which no agent of the scope ran (a session with no known end counts as zero)
    runs = sorted((s[0], s[1] if s[1] is not None else s[0]) for spans in sess.values() for s in spans)
    gaps = []   # (start, end) of every such stretch, for the Waiting lane (HM-18)
    if runs:
        horizon = max(e for _, e in runs) if terminal else max(now_e, runs[0][0])
        covered, (cur0, cur1) = 0, runs[0]
        for s0, s1 in runs[1:]:
            if s0 > cur1:
                gaps.append((cur1, s0))
                covered += cur1 - cur0
                cur0, cur1 = s0, s1
            else:
                cur1 = max(cur1, s1)
        covered += min(cur1, horizon) - cur0
        wait_total = max(0, round(horizon - runs[0][0] - covered))
        if horizon > cur1:
            gaps.append((cur1, horizon))
    if waiting:
        ends = [s[1] for spans in sess.values() for s in spans if s[1] is not None]
        wait_s = round(now_e - max(ends)) if ends and now_e >= max(ends) else None
        in_ci = [w["task_id"] for w in cg_waits if w["open"]]
        in_queue = [w["task_id"] for w in pc_waits if w["open"]]
        wait_note = (f"{WAIT_REVIEW}: {', '.join(in_ci)}" if in_ci
                     else f"{WAIT_QUEUE}: {', '.join(in_queue)}" if in_queue else WAIT_UNKNOWN)
        pr_of = {t["id"]: t["pr_url"] for t in tasks}
        wait_links = [{"label": f"{WAIT_LINK_LABEL} {tid}", "url": pr_of[tid]} for tid in in_ci if is_pr_url(pr_of.get(tid))]
    if gaps:   # the lane list above holds this same rows list
        rows_by_lane[Lane.WAIT].append({"name": WAIT_ROW, "task_id": None, "spans": [
            {"start_s": off(g0), "end_s": off(g1), "kind": SpanKind.WAIT,
             "note": wait_note if waiting and i == len(gaps) - 1 else None} for i, (g0, g1) in enumerate(gaps)]})
    nodes = []
    for nid, label in NODES:
        mine = [a for a in agents if _LANE_NODE.get(_ROLE_LANE.get(a["role"])) == nid]
        works = [work_of(a["name"]) for a in mine]
        live = any(a["status"] in LIVE_STATUSES for a in mine)
        if nid == Node.WAIT:
            state = State.LIVE if waiting else State.IDLE
        elif nid == Node.MAIN:
            state = State.DONE if merged else State.PENDING
        elif live:
            state = State.LIVE
        elif open_fail.get(nid):
            state = State.FAIL
        elif mine:
            state = State.DONE
        elif nid == Node.JUDGE and not judged:
            state = State.PENDING
        else:
            state = State.IDLE
        nodes.append({"id": nid, "label": label, "state": state,
                      "work_s": wait_total if nid == Node.WAIT else sum(works) if mine and all(w is not None for w in works) else None,
                      "current_s": wait_s if nid == Node.WAIT else None,   # the wait going on now; work_s is every wait so far
                      "note": wait_note if nid == Node.WAIT else None,
                      "links": wait_links if nid == Node.WAIT else [],
                      "tokens": None, "cost": None, "cost_note": COST_NOTE,
                      "agents": [{"name": a["name"], "status": a["status"], "work_s": w, "cost": None, "task_id": a["task_id"],
                                  "session_id": a["session_id"], "after_last_event": None} for a, w in zip(mine, works)]})

    status = head["status"]
    last_e = max((q._epoch(ev["ts"]) for ev in events if q._epoch(ev["ts"]) is not None), default=None)
    end_e = (last_e if terminal else now_e)
    known = [w for n in nodes for w in (a["work_s"] for a in n["agents"]) if w is not None]
    return {"scope": scope, "id": oid, "title": head["title"], "status": status, "goal_id": goal_id,
            "start": start, "now": now_d.isoformat(timespec="seconds"), "show_text": bool(show_text),
            "elapsed_s": round(end_e - start_e) if end_e is not None and start_e is not None and end_e >= start_e else None,
            "totals": {"agent_s": sum(known) if known else None,
                       "tokens": None, "cost": None, "cost_as_of": None, "cost_note": COST_NOTE, "unattributed_cost": None,
                       "rejections": rejections, "messages": n_msgs},
            "nodes": nodes, "groups": [{"id": gid, "label": label, "nodes": list(members)} for gid, label, members in GROUPS],
            "edges": edges, "lanes": lanes, "events": events, "findings": [], "phases": []}
