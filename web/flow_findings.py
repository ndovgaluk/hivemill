"""Findings and Sequence phases for the flow debugger (DVDG-560), computed from a web/flow.py payload after
web/flowcost.fill. Read-only. A null (unknown) time or cost never produces a finding: unknown is not zero and not slow.

Phases (grilling DVDG-552): goal scope = "Goal setup" (steps before the first task's first step), one phase per task in
order of first activity (task-less steps in between go to the task active at that time), "Wrap-up" (after the last
task's last step). Task scope = Spec, Coding attempt N (each coder session start), Review and QA attempt N (each
in_review round), Merge. Every event lands in exactly one phase; empty phases are left out.
"""
from bisect import bisect_right

from web import flow as F
from web import queries as q


class Kind:
    LONG_WAIT, REJECTIONS, UNSTAFFED_REVIEW = "long_wait", "rejections", "unstaffed_review"
    MISSING_START, UNATTRIBUTED, OVERHEAD = "missing_start", "unattributed_cost", "goal_overhead"


WAIT_WARN_S, WAIT_BAD_S = F.WAIT_WARN_S, F.WAIT_BAD_S   # one set of thresholds for edges and findings
REVIEW_WARN_S = 60          # PR open with no reviewer or QA started for this long
SHARE_WARN = 0.25           # unattributed or overhead cost at or above this share of the total
SEV_RANK = {F.Severity.BAD: 0, F.Severity.WARN: 1, F.Severity.OK: 2}
SIZE = "_size"              # sort key inside a finding; removed before the payload is returned
DEFAULT_SIZE = 0.5          # a finding whose effect cannot be compared (no elapsed time) sorts in the middle


class PhaseTitle:
    SETUP, WRAP_UP = "Goal setup", "Wrap-up"
    SPEC, CODING, REVIEW, MERGE = "Spec", "Coding attempt {n}", "Review and QA attempt {n}", "Merge"


PHASE_ID = "p{n}"
STAGE_SPEC, STAGE_REVIEW = "spec", "review"     # web.queries.task_lifecycle stage names


def fmt_s(s):
    s = int(s)
    if s >= 3600:
        return f"{s // 3600}h {s % 3600 // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s}s"


def money(c):
    return f"${c:,.2f}"


def _finding(sev, text, target_kind, target_id, node, kind, size):
    return {"severity": sev, "text": text, "target": {"kind": target_kind, "id": target_id}, "node": node, "kind": kind,
            SIZE: size}


def _edge(d, eid):
    return next(e for e in d["edges"] if e["id"] == eid)


def _share(part, whole):
    return part / whole if part is not None and whole else None


# ── detectors: each returns a list ──

def long_wait(d):
    ws = [w for w in _edge(d, F.Edge.PC)["waits"] if w["wait_s"] is not None]
    if not ws:
        return []
    w = max(ws, key=lambda x: x["wait_s"])
    if w["wait_s"] < WAIT_WARN_S:
        return []
    share = _share(w["wait_s"], d["elapsed_s"])
    text = f"{w['task_id']} waited {fmt_s(w['wait_s'])} before coding" + (" (still queued)" if w["open"] else "")
    if share is not None and share <= 1:
        text += f", {round(share * 100)}% of elapsed"
    sev = F.Severity.BAD if w["wait_s"] >= WAIT_BAD_S else F.Severity.WARN
    return [_finding(sev, text, F.FindingTarget.EDGE, F.Edge.PC, F.Node.CODERS, Kind.LONG_WAIT,
                     share if share is not None else DEFAULT_SIZE)]


def rejections(d):
    """HM-17: one finding per role that rejected (Reviewer, QA, Judge), on that role's box."""
    rej = [e for e in d["events"] if e["kind"] == F.EventKind.VERDICT and e["severity"] == F.Severity.BAD]
    if not rej:
        return []
    merged = {e["task_id"] for e in d["events"] if e["edge"] == F.Edge.JM}
    labels = dict(F.NODES)
    out = []
    for node in dict.fromkeys(e["from_node"] for e in rej):   # first-rejection order
        last = {}
        for e in d["events"]:      # events are in time order: this role's last verdict per task wins
            if e["kind"] == F.EventKind.VERDICT and e["from_node"] == node:
                last[e["task_id"]] = e["severity"]
        still = sorted(t for t, sev in last.items() if sev == F.Severity.BAD and t not in merged)
        n = sum(e["from_node"] == node for e in rej)
        by = f" by {labels[node]}" if node in labels else ""
        text = (f"{n} rejection{'s' if n != 1 else ''}{by}, "
                + (f"{len(still)} still open ({', '.join(still)})" if still else "all resolved"))
        target = (F.FindingTarget.EDGE, F.Edge.RW) if node in F.GATE_NODES else (F.FindingTarget.NODE, node)
        out.append(_finding(F.Severity.BAD if still else F.Severity.WARN, text, *target, node, Kind.REJECTIONS, float(n)))
    return out


def unstaffed_review(d):
    ws = [w for w in _edge(d, F.Edge.CG)["waits"] if w["wait_s"] is not None and w["wait_s"] >= REVIEW_WARN_S]
    if not ws:
        return []
    w = max(ws, key=lambda x: x["wait_s"])
    nudge = next((e for e in d["events"] if e["from_node"] == F.Node.DIRECTOR and e["to_node"] == F.Node.LEAD
                  and e["t_s"] is not None and w["start_s"] is not None and w["end_s"] is not None
                  and w["start_s"] <= e["t_s"] <= w["end_s"]), None)
    text = f"PR of {w['task_id']} waited {fmt_s(w['wait_s'])} with no reviewer or QA started"
    text += " (still waiting)" if w["open"] else (" until the director nudged the lead" if nudge else "")
    target = (F.FindingTarget.EVENT, nudge["id"]) if nudge else (F.FindingTarget.EDGE, F.Edge.CG)
    # the wait is "no reviewer or QA started": both are unstaffed, the badge goes on the first box of the gate
    return [_finding(F.Severity.WARN, text, *target, F.Node.REVIEWER, Kind.UNSTAFFED_REVIEW,
                     _share(w["wait_s"], d["elapsed_s"]) or DEFAULT_SIZE)]


def missing_start(d):
    return [_finding(F.Severity.WARN, f"{w['task_id']}: no coder start was recorded, so its coding time is unknown",
                     F.FindingTarget.NODE, F.Node.CODERS, F.Node.CODERS, Kind.MISSING_START, DEFAULT_SIZE)
            for w in _edge(d, F.Edge.PC)["waits"] if w["wait_s"] is None and w["note"] == F.NOTE_NO_CODER_START]


def unattributed(d):
    t = d["totals"]
    share = _share(t.get("unattributed_cost"), t.get("cost"))
    if share is None or share < SHARE_WARN:
        return []
    return [_finding(F.Severity.WARN, f"{money(t['unattributed_cost'])} of {money(t['cost'])} is not attributed to any agent",
                     F.FindingTarget.NODE, F.Node.LEAD, F.Node.LEAD, Kind.UNATTRIBUTED, share)]


def overhead(d):
    t = d["totals"]
    if d["scope"] != F.Scope.GOAL:
        return []
    share = _share(t.get("overhead_cost"), t.get("cost"))
    if share is None or share < SHARE_WARN:
        return []
    return [_finding(F.Severity.WARN, f"{money(t['overhead_cost'])} of {money(t['cost'])} is goal overhead (HQ and lead)",
                     F.FindingTarget.NODE, F.Node.LEAD, F.Node.LEAD, Kind.OVERHEAD, share)]


DETECTORS = (long_wait, rejections, unstaffed_review, missing_start, unattributed, overhead)


def findings(d):
    out = [f for det in DETECTORS for f in det(d)]
    out.sort(key=lambda f: (SEV_RANK[f["severity"]], -f[SIZE]))
    for f in out:
        del f[SIZE]
    return out


# ── phases ──

SUMMARY_NAMES = 3   # senders named in a phase summary; the rest are counted


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _summary(evs, span):
    """One sentence: who acted, then what (the card shows the time range and the action count itself)."""
    who = []
    for e in evs:
        name = e["from"] or e["from_node"]
        if name and name not in who:
            who.append(name)
    named = who[:SUMMARY_NAMES]
    names = (", ".join(named[:-1]) + " and " + named[-1]) if len(named) > 1 else (named[0] if named else "")
    if len(who) > SUMMARY_NAMES:
        names = f"{', '.join(named)} and {len(who) - SUMMARY_NAMES} more"
    msgs = sum(e["kind"] == F.EventKind.MSG for e in evs)
    verdicts = [e for e in evs if e["kind"] == F.EventKind.VERDICT]
    rej = sum(e["severity"] == F.Severity.BAD for e in verdicts)
    status = sum(e["kind"] == F.EventKind.STATUS for e in evs)
    parts = [_plural(msgs, "message")] if msgs else []
    if verdicts:
        parts.append(_plural(len(verdicts), "verdict") + (f" ({rej} rejected)" if rej else ""))
    if status:
        parts.append(_plural(status, "status update"))
    return f"{names}: {', '.join(parts)}." if names else f"{', '.join(parts)}."


ANY_TASK = object()   # a phase whose agent sessions may belong to any task (task scope)


def _phase_list(d, groups):
    """groups: [(title, [events], task id | None | ANY_TASK)] in order → phase dicts with span refs (the agent
    sessions of that task, None = goal-level rows only); empty groups dropped."""
    out = []
    for title, evs, task in groups:
        if not evs:
            continue
        ts = [e["t_s"] for e in evs if e["t_s"] is not None]
        lo, hi = (min(ts), max(ts)) if ts else (None, None)
        refs = [{"lane": lane["id"], "row": row["name"], "index": i}
                for lane in d["lanes"] for row in lane["rows"] for i, sp in enumerate(row["spans"])
                if lane["id"] != F.Lane.WAIT   # a wait is not a session (HM-18)
                and lo is not None and sp["start_s"] is not None and lo <= sp["start_s"] <= hi
                and (task is ANY_TASK or row["task_id"] == task)]
        out.append({"id": PHASE_ID.format(n=len(out) + 1), "title": title,
                    "summary": _summary(evs, hi - lo if ts else None), "event_ids": [e["id"] for e in evs], "span_refs": refs})
    return out


def _goal_phases(d, con):
    evs = d["events"]
    first, last = {}, {}
    for e in evs:
        if e["task_id"] and e["t_s"] is not None:
            first[e["task_id"]] = min(first.get(e["task_id"], e["t_s"]), e["t_s"])
            last[e["task_id"]] = max(last.get(e["task_id"], e["t_s"]), e["t_s"])
    order = sorted(first, key=lambda t: (first[t], t))
    starts = [first[t] for t in order]
    titles = {r["id"]: r["title"] for r in q._in(con, "SELECT id, title FROM tasks WHERE id IN ({in})", order)}
    groups = {t: [] for t in order}
    setup, wrap = [], []
    end = max(last.values(), default=None)
    for e in evs:
        if e["task_id"] in groups:
            groups[e["task_id"]].append(e)
        elif not order or e["t_s"] is None or e["t_s"] < starts[0]:
            setup.append(e)
        elif e["t_s"] > end:
            wrap.append(e)
        else:
            groups[order[bisect_right(starts, e["t_s"]) - 1]].append(e)
    # a task's phase lists only that task's agent sessions; setup and wrap-up only goal-level ones (no task)
    return _phase_list(d, [(PhaseTitle.SETUP, setup, None), *((f"{t}: {titles.get(t, '')}".rstrip(": "), groups[t], t) for t in order),
                           (PhaseTitle.WRAP_UP, wrap, None)])


def _task_phases(d, con, now):
    start_e = q._epoch(d["start"])
    rel = (lambda ts: round(q._epoch(ts) - start_e) if q._epoch(ts) is not None and start_e is not None else None)
    marks = [(float("-inf"), PhaseTitle.SPEC)]
    coder_starts = sorted(sp["start_s"] for lane in d["lanes"] if lane["id"] == F.Lane.CODERS for row in lane["rows"]
                          if row["task_id"] == d["id"] for sp in row["spans"]
                          if sp["kind"] != F.SpanKind.WAIT and sp["start_s"] is not None)
    marks += [(s, PhaseTitle.CODING.format(n=i + 1)) for i, s in enumerate(coder_starts)]
    lc = q.task_lifecycle(con, d["id"], now) or {"stages": []}
    reviews = sorted(r for r in (rel(st["start"]) for st in lc["stages"] if st["stage"] == STAGE_REVIEW) if r is not None)
    marks += [(s, PhaseTitle.REVIEW.format(n=i + 1)) for i, s in enumerate(reviews)]
    merges = [e["t_s"] for e in d["events"] if e["edge"] == F.Edge.JM and e["t_s"] is not None]
    if merges:
        marks.append((min(merges), PhaseTitle.MERGE))
    marks.sort(key=lambda m: m[0])
    times = [m[0] for m in marks]
    groups = [(title, [], ANY_TASK) for _, title in marks]
    for e in d["events"]:
        i = 0 if e["t_s"] is None else max(0, bisect_right(times, e["t_s"]) - 1)
        groups[i][1].append(e)
    return _phase_list(d, groups)


def phases(d, con, now=None):
    return _goal_phases(d, con) if d["scope"] == F.Scope.GOAL else _task_phases(d, con, now)


def attach(d, con, now=None):
    """Fill d["findings"] and d["phases"] in place; returns d."""
    d["findings"] = findings(d)
    d["phases"] = phases(d, con, now)
    return d
