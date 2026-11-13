"""Tokens and cost per box and per step for the flow debugger (DVDG-555), filled into a web/flow.py payload.

Rule (grilling DVDG-552): a step's usage is its agent's session usage lines timestamped after that agent's previous
timeline step, up to and including this one. A model request is one log line with one timestamp, so it is never split.
"Previous step" is looked up in the whole DB (messages sent, verdicts written, timeline events acted), not only in this
payload, so a goal-level agent (the lead on a task page) is not charged for work on other tasks. Lines before the
agent's first step go to that step; lines after its last step form `after_last_event`. Sessions come from
web.tokens.attribute (the same mapping task_usage uses), subagent logs count towards their session, and DB times
(local offset) and log times (UTC) are compared as aware datetimes. Unknown stays None with a note, never 0.
"""
import bisect
import json
import os
import re
import threading

from web import tokens as tk
from web.flow import TIMELINE_ACTIONS, Action, Key, Scope
from web.prices import PRICES_AS_OF, cost

MAX_READ_BYTES = tk.MAX_READ_BYTES   # per log file and request; a bigger file makes its agent's values unknown
SID_RE = re.compile(r"[A-Za-z0-9._-]+")
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")
FAST = "fast"
UNATTRIBUTED = "unattributed"      # web.tokens bucket name for sessions mapped to no agent


class Note:
    NO_INDEX = "token index not ready yet"
    NO_SESSION = "no session log found for {agent}"
    CURSOR = "Cursor agents record no token usage"
    TRUNCATED = "session log larger than the read cap ({cap} bytes): not read in full"
    UNREADABLE = "session log could not be read"
    UNPRICED = "a model in this step has no price"
    NOT_AN_AGENT = "sender is not an agent of this {scope}"
    PARTIAL = "unknown for: {agents}"


class LineCache:
    """Per-file usage lines, re-read only when the file's inode, size or mtime changed. Counters for tests."""

    def __init__(self):
        self._files = {}
        self._lock = threading.Lock()
        self.bytes_read = 0
        self.files_read = 0

    def read(self, path, confine=None):
        """(lines, truncated) of one log file, or None when it cannot be opened. A line: web.tokens.usage_line + "t"."""
        f = None
        try:
            if confine is not None:
                f = tk.TokenIndex._open_confined(path, confine)   # same worker-file confinement as the index
                if f is None:
                    return None
                st = os.fstat(f.fileno())
            else:
                st = os.stat(path)
            sig = (st.st_ino, st.st_size, st.st_mtime_ns)
            with self._lock:
                hit = self._files.get(path)
            if hit is not None and hit[0] == sig:
                return hit[1], hit[2]
            if f is None:
                f = open(path, "rb")
            data = f.read(min(st.st_size, MAX_READ_BYTES))
        except OSError:
            return None
        finally:
            if f is not None:
                f.close()
        lines = []
        for raw in data.split(b"\n"):
            if tk.USAGE_MARK not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue                 # also a line cut by the read cap
            if not isinstance(d, dict) or d.get("type") != tk.ASSISTANT:
                continue
            x = tk.usage_line(d)
            if x is None:
                continue
            t = tk._parse_ts(x["ts"])
            x["t"] = t.timestamp() if t else None
            x["key"] = tuple(x["key"]) if isinstance(x["key"], list) else x["key"]
            lines.append(x)
        truncated = st.st_size > MAX_READ_BYTES
        with self._lock:
            self._files[path] = (sig, lines, truncated)
            self.bytes_read += len(data)
            self.files_read += 1
        return lines, truncated


CACHE = LineCache()


class Usage:
    """What the flow cost needs from the token index: its snapshot (for session → agent) and where the logs live."""

    def __init__(self, snapshot, index=None, cache=None):
        self.snapshot = snapshot or {}
        self.cache = cache or CACHE
        self.roots = (index.root, index.extra_roots, index.workers_root) if index is not None else (None, (), None)

    def ready(self):
        return bool(self.snapshot.get("ready"))

    def session_lines(self, sid):
        """(lines in time order, problem note or None) of one session: its main log and subagent logs, deduplicated."""
        if not SID_RE.fullmatch(sid or ""):
            return None, Note.UNREADABLE
        found = tk.TokenIndex(self.roots[0], self.roots[1], self.roots[2], only_session=sid)._discover()
        if not found:
            return None, None
        seen, out = set(), []
        for path, _s, _p, _sub, confine in sorted(found, key=lambda x: (x[3], str(x[0]))):   # main log first
            r = self.cache.read(path, confine)
            if r is None:
                return None, Note.UNREADABLE
            lines, truncated = r
            if truncated:
                return None, Note.TRUNCATED.format(cap=MAX_READ_BYTES)
            for x in lines:
                if x["key"] is not None:
                    if x["key"] in seen:
                        continue
                    seen.add(x["key"])
                out.append(x)
        out.sort(key=lambda x: (x["t"] is None, x["t"] or 0.0))
        return out, None


class _Acc:
    """Usage of one step: token counts per (model, fast) so each group is priced with its own rates."""

    def __init__(self):
        self.groups = {}

    def add(self, x):
        g = self.groups.setdefault((x["model"], x["fast"]), dict.fromkeys(tk.USAGE_FIELDS, 0))
        for k in tk.USAGE_FIELDS:
            g[k] += x[k]

    def merge(self, other):
        for key, g in other.groups.items():
            mine = self.groups.setdefault(key, dict.fromkeys(tk.USAGE_FIELDS, 0))
            for k in tk.USAGE_FIELDS:
                mine[k] += g[k]

    def tokens(self):
        t = dict.fromkeys(TOKEN_KEYS, 0)
        for g in self.groups.values():
            t["input"] += g["input"]
            t["output"] += g["output"]
            t["cache_read"] += g["cache_read"]
            t["cache_write"] += g["cache_write_5m"] + g["cache_write_1h"]
        return t

    def cost(self):
        """USD, or None when a group with tokens has no price."""
        total = 0.0
        for (model, fast), g in self.groups.items():
            c = cost(model, g, FAST if fast else None)
            if c is None:
                if any(g.values()):
                    return None
                continue
            total += c
        return round(total, 6)


def _epoch(ts):
    t = tk._parse_ts(ts)
    return t.timestamp() if t else None


def _agent_steps(con, name):
    """(epoch, step key) of every timeline step the agent made anywhere in the DB, in time order."""
    acts = ",".join("?" * len(TIMELINE_ACTIONS))
    out = [(_epoch(r[1]), f"{Key.MESSAGE}{r[0]}") for r in con.execute("SELECT id, created FROM messages WHERE sender=?", (name,))]
    out += [(_epoch(r[1]), f"{Key.VERDICT}{r[0]}") for r in con.execute("SELECT id, created FROM verdicts WHERE author=?", (name,))]
    out += [(_epoch(r[1]), f"{Key.EVENT}{r[0]}") for r in con.execute(
        f"SELECT id, ts FROM events WHERE action IN ({acts}) AND (actor=? OR (entity='agent' AND entity_id=? AND action=?))",
        (*TIMELINE_ACTIONS, name, name, Action.DONE))]
    return sorted((e, k) for e, k in out if e is not None)


def _set(target, tokens, c, note=None, exact=None):
    target["tokens"], target["cost"], target["cost_note"] = tokens, c, note
    if exact is not None:
        target["cost_exact"] = exact


def fill(d, con, usage):
    """Fill tokens and cost on the events, agents, nodes and totals of payload `d` (web.flow.build) in place."""
    events = d["events"]
    if not usage.ready():
        for x in [*events, *d["nodes"], d["totals"]]:
            x["cost_note"] = Note.NO_INDEX
        return d
    snap = usage.snapshot
    attr = tk.attribute(snap, con)
    sessions_of = {}
    for sid, a in attr.items():
        if a["agent"]:
            sessions_of.setdefault(a["agent"], []).append(sid)
    rows = tk._usage_agents(con)
    by_from = {}
    for ev in events:
        by_from.setdefault(ev["from"], []).append(ev)
    scope_id = d["id"]
    seen = set()
    for node in d["nodes"]:
        known, unknown = [], []
        for ag in node["agents"]:
            name = ag["name"]
            seen.add(name)
            own = d["scope"] != Scope.TASK or ag["task_id"] == scope_id   # a goal-level agent on a task page: its steps only
            mine = by_from.get(name, [])
            note = None
            lines = None
            if name in rows and tk._is_cursor(rows[name]):
                note = Note.CURSOR
            elif not sessions_of.get(name):
                note = Note.NO_SESSION.format(agent=name)
            else:
                lines = []
                for sid in sessions_of[name]:
                    got, problem = usage.session_lines(sid)
                    if got is None:
                        note, lines = problem or Note.NO_SESSION.format(agent=name), None
                        break
                    lines += got
            if lines is None:
                for ev in mine:
                    _set(ev, None, None, note, False)
                ag["cost"], ag["tokens"], ag["cost_note"], ag["after_last_event"] = None, None, note, None
                unknown.append(name)
                continue
            steps = _agent_steps(con, name)
            ids = {ev["id"] for ev in mine}
            keyed = {k for _, k in steps}
            steps = sorted(steps + [(e, ev["id"]) for ev in mine if ev["id"] not in keyed for e in [_epoch(ev["ts"])] if e is not None])
            times = [e for e, _ in steps]
            acc = {ev["id"]: _Acc() for ev in mine}
            after, outside = _Acc(), _Acc()
            for x in lines:
                if x["t"] is None:
                    outside.add(x)
                    continue
                i = bisect.bisect_left(times, x["t"])
                if i >= len(steps):
                    after.add(x)
                elif steps[i][1] in ids:
                    acc[steps[i][1]].add(x)
                else:
                    outside.add(x)       # a step of this agent that this page does not show (another task)
            total = _Acc()
            for ev in mine:
                a = acc[ev["id"]]
                c = a.cost()
                _set(ev, a.tokens(), c, None if c is not None else Note.UNPRICED, c is not None)
                total.merge(a)
            if own:
                total.merge(after)
            ac = after.cost()
            ag["after_last_event"] = {"tokens": after.tokens(), "cost": ac} if own else None
            ag["outside"] = {"tokens": outside.tokens(), "cost": outside.cost()}
            ag["tokens"], ag["cost"] = total.tokens(), total.cost()
            ag["cost_note"] = None if ag["cost"] is not None else Note.UNPRICED
            if ag["cost"] is not None:
                known.append(ag)
            else:
                unknown.append(name)
        if known:
            node["cost"] = round(sum(a["cost"] for a in known), 6)
            node["tokens"] = {k: sum(a["tokens"][k] for a in known) for k in TOKEN_KEYS}
            node["cost_note"] = Note.PARTIAL.format(agents=", ".join(unknown)) if unknown else None
        else:
            node["cost"], node["tokens"] = None, None
            node["cost_note"] = Note.PARTIAL.format(agents=", ".join(unknown)) if unknown else None
    for ev in events:
        if ev["from"] not in seen:
            _set(ev, None, None, Note.NOT_AN_AGENT.format(scope=d["scope"]), False)
    if d["scope"] == Scope.TASK:
        u = tk.task_usage(snap, attr, con, scope_id)
        rows_all = u["rows"]
    else:
        u = tk.goal_usage(snap, attr, con, scope_id)
        rows_all = u["overhead"]["rows"] + [r for t in u["tasks"].values() for r in t["rows"]]
    tot = u["totals"] or {}
    t = d["totals"]
    t["cost"] = tot.get("cost")
    t["tokens"] = {k: tot[k] for k in TOKEN_KEYS} if tot.get("input") is not None else None
    t["cost_as_of"] = PRICES_AS_OF
    t["cost_note"] = None if t["cost"] is not None else Note.UNPRICED
    # goal overhead (HQ, lead, sessions of the goal without a task); a task has none of its own
    t["overhead_cost"] = (u["overhead"]["totals"] or {}).get("cost") if d["scope"] == Scope.GOAL else None
    un = [r["cost"] for r in rows_all if r["agent"] == UNATTRIBUTED]
    t["unattributed_cost"] = (None if any(c is None for c in un) else round(sum(un), 6)) if un else 0.0
    return d
