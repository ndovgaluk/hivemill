"""Settings page (HM-1): curated global factory settings, in groups.

Editable only while `factory serve` is bound to a loopback address: then each setting has a small form that POSTs to
/settings, and the server runs `bin/factory config <key> <value>`, so the CLI's validation, role check and `config set`
event stay the only write path (the server itself keeps its read-only DB connection). On a LAN bind the page is
read-only and shows the command instead.
"""
import os
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

from web.components import section
from web.html import el
from web.db import has_column
from web.queries import parse_ts

TITLE = "Settings"
REFRESH = False          # a 60 s reload would wipe a half-filled form
FORMS = True             # the server sends form-action 'self' and a same-origin referrer policy for this page only

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_TIMEOUT_S = 10
MSG_MAX = 200
VALUE_MAX = 64


class Kind:
    SWITCH = "switch"    # "0" / "1"
    INT = "int"
    CHOICE = "choice"    # one of Setting.options; the CLI does not validate these keys, so the page must
    URL = "url"          # HM-45: an http(s) address; the page checks the shape and the CLI checks it again


ON, OFF = "1", "0"
Setting = namedtuple("Setting", "key label help kind lo hi options", defaults=(None,))


class Label:
    OFF = "Off"
    ON = "On"
    SHADOW = "Shadow (events only)"


# option values are the ones DEFAULT_CONFIG and bin/flags.json document for each key
OFF_ON = (("off", Label.OFF), ("on", Label.ON))
OFF_SHADOW_ON = (("off", Label.OFF), ("shadow", Label.SHADOW), ("on", Label.ON))
GROUPS = (
    ("Worktrees", "How coder tasks get their git worktree. Details: docs/worktree-reuse.md.", (
        Setting("worktree_reuse", "Reuse coder worktrees",
                "On: factory clean keeps a merged task's clean worktree in a pool and the next coder task of the same "
                "project reuses it (ignored files such as node_modules stay). Off: every coder task gets a fresh "
                "worktree, deleted after merge.", Kind.SWITCH, None, None),
        Setting("worktree_pool_max", "Free worktrees kept per project",
                "How many unused worktrees factory clean keeps per project while reuse is on.", Kind.INT, 0, 50),
    )),
    ("Automation", "Steps the tick can do itself instead of a lead or a judge agent. All are off by default. Each "
                   "applies from the next tick; Off is the rollback.", (
        Setting("lead_parking", "Lead parking",
                "On: a lead with nothing to do may park (factory park); its pane is closed and unread mail wakes a "
                "fresh lead. Off: leads stay live. Details: docs/lead-parking.md.", Kind.SWITCH, None, None),
        Setting("lead_less_dispatch", "Start workers without the lead",
                "On: the tick starts workers for ready tasks of a parked team and only informs the lead. Shadow: "
                "records what it would start. Needs lead parking. Details: docs/lead-less-dispatch.md.",
                Kind.CHOICE, None, None, ((OFF, Label.OFF), ("shadow", Label.SHADOW), (ON, Label.ON))),
        Setting("review_autospawn", "Start review when a PR opens",
                "On: the tick starts the reviewer and QA when a coder's PR opens, and again on a new green head. "
                "Details: docs/review-autospawn.md.", Kind.CHOICE, None, None, OFF_ON),
        Setting("coder_ci_handoff", "Coder hands off at PR open",
                "The coder finishes at PR open without waiting for CI; the tick starts review at green and, on a red "
                "head, restarts the coder: Resume continues its session, Fresh starts a new one. Works only with "
                "review autospawn on and the PR check required. Details: docs/prcheck.md.", Kind.CHOICE, None, None,
                (("off", Label.OFF), ("resume", "Resume the same session"), ("fresh", "Fresh session"))),
        Setting("prcheck_required", "PR check required before done",
                "On: a coder's factory done on a task with a PR needs a passing factory prcheck on its head. The "
                "coder hand-off above needs it. Details: docs/prcheck.md.", Kind.SWITCH, None, None),
        Setting("risk_tiers", "Risk tiers",
                "On: a PR's risk tier (T0 to T3) is computed. The mechanical merger and the combined reviewer and QA "
                "agent for low tiers need it.", Kind.CHOICE, None, None, OFF_ON),
        Setting("mech_merge", "Merge without a judge agent",
                "On: the tick merges tier T0 to T2 PRs through the judge's own gate, with no judge agent. Shadow: "
                "runs the gate and records what it would do. Needs risk tiers. Details: docs/mech-merge.md.",
                Kind.CHOICE, None, None, OFF_SHADOW_ON),
        Setting("hand_merge_accept", "Accept pull requests merged by hand on GitHub",
                "On: the hourly drift check closes a task in review whose pull request GitHub reports merged, after "
                "checking that the merge commit is on the base branch. Such a merge bypasses the factory's merge gate "
                "(no judge, no gate checks) and is recorded as a hand merge on the task page. Details: "
                "docs/hand-merge.md.", Kind.CHOICE, None, None, OFF_ON),
        Setting("workflow_engine", "Workflow engine",
                "On: the factory builds the workflow engine and the tick runs it, for stories started with factory wf. "
                "Off: nothing of it runs. Details: docs/workflow-engine.md.", Kind.CHOICE, None, None, OFF_ON),
        Setting("workflow_reviewer_session", "Reviewer session in story runs",
                "A fresh reviewer for each child: every child and every fix round is read by a new reviewer. Keep one "
                "reviewer for the story: the same reviewer session is resumed for each child and remembers the earlier "
                "ones. Applies from the next review. Details: docs/workflow-engine.md.", Kind.CHOICE, None, None,
                (("fresh", "A fresh reviewer for each child"), ("keep", "Keep one reviewer for the story"))),
        Setting("tsr_web_url", "TSR base URL",
                "Taskosaur's base address, for example http://localhost:4001/<workspace>/<project>. A story run's goal then "
                "links its TSR story and children to {address}/tasks/{key} (new tab). Empty: the keys are plain text. Details: docs/workflow-engine.md.",
                Kind.URL, None, None),
        Setting("workflow_ci", "CI for new story runs",
                "GitHub: the run opens one pull request, GitHub's checks and the judge clear it. Local: only the tests "
                "the change can affect run on this machine, then the run merges into main itself. None: no pull request "
                "and no tests, the run merges into main as soon as every child is reviewed. Applies to runs started "
                "after the change; factory wf start --ci overrides it. Details: docs/workflow-engine.md.",
                Kind.CHOICE, None, None, (("github", "GitHub"), ("local", "Local (affected tests)"),
                                          ("none", "None (no PR, no tests)"))),
    )),
    # HM-53: the per-project rows of this group (what clears a change, the last local run) are drawn by _gate_row
    ("Merge gate", "What clears a change before it merges, per project: GitHub's CI, or the local test run of "
                   "docs/local-gate.md (section \"This factory\"). The local full suite takes about 30 min on this "
                   "machine, GitHub's CI about 22. Details: docs/local-gate.md.", (
        Setting("gate_ignore_pending_ci", "Nothing waits for GitHub in local mode",
                "On: for a project on the local test run, the merge, the first review and the coder's pre-check wait "
                "only for the local run; a GitHub check that finished red still blocks a merge. No effect on a "
                "project on GitHub CI. Details: docs/local-gate.md.", Kind.SWITCH, None, None),
    )),
)
MERGE_GATE_GROUP = "Merge gate"


class GateMode:
    GITHUB = "github"
    LOCAL = "local"
    CUSTOM = "custom"   # a gate_cmd this page did not set: shown, never changed here


GATE_MODE_LABELS = {GateMode.GITHUB: "GitHub CI", GateMode.LOCAL: "Local test run", GateMode.CUSTOM: "Custom command"}
GATE_CHOICES = (GateMode.GITHUB, GateMode.LOCAL)
# the values HM-51 measured and wrote down in docs/local-gate.md, section "This factory"
LOCAL_GATE_CMD = "python3 $FACTORY_MAIN/tests/gate_shards.py"
LOCAL_GATE_COUNT_CMD = "python3 $FACTORY_MAIN/ci/test_count_gate.py count ."
LOCAL_GATE_TIMEOUT_S = 3600
GATE_PATH = "/settings/gate"   # the page's second write path (server: Handler._gate_post)
PROJECT_MAX = 64
SETTINGS = {s.key: s for _, _, items in GROUPS for s in items}
EDITABLE = frozenset(SETTINGS)


def valid_value(key, value):
    """True when `value` is one the page offers for `key`. An integer's range stays with the CLI, which names it."""
    s = SETTINGS[key]
    if s.kind == Kind.CHOICE:
        return value in dict(s.options)
    if s.kind == Kind.SWITCH:
        return value in (ON, OFF)
    if s.kind == Kind.URL:
        return bool(_URL_RE.fullmatch(value))
    return value.isascii() and value.isdigit()

# query parameters of the redirect after a change (server: Handler._settings_post and Handler._gate_post)
Q_SAVED, Q_ERROR, Q_MSG = "saved", "error", "msg"
Q_GATE_SAVED, Q_GATE_ERROR = "gate_saved", "gate_error"


def _run_factory(factory_home, args, env, what):
    """Run `bin/factory <args>`; returns (ok, message): the CLI's last stderr line on a refusal."""
    cmd = [sys.executable, str(ROOT / "bin" / "factory"), *args]
    run_env = dict(os.environ if env is None else env)
    if factory_home:
        run_env["FACTORY_HOME"] = str(factory_home)
    try:
        r = subprocess.run(cmd, env=run_env, capture_output=True, text=True, timeout=CONFIG_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"{what} could not run: {e}"[:MSG_MAX]
    if r.returncode == 0:
        return True, ""
    last = (r.stderr.strip().splitlines() or [f"{what} exited {r.returncode}"])[-1]
    return False, last.removeprefix("factory: ")[:MSG_MAX]


def apply_change(factory_home, key, value, env=None):
    """Run `bin/factory config <key> <value>`; returns (ok, message). The caller has checked `key` is in EDITABLE."""
    return _run_factory(factory_home, ["config", key, value], env, "factory config")


def gate_mode(gate_cmd):
    cmd = (gate_cmd or "").strip()
    return GateMode.GITHUB if not cmd else GateMode.LOCAL if cmd == LOCAL_GATE_CMD else GateMode.CUSTOM


def gate_update_args(project, mode):
    """`factory project update` arguments for `mode`. GitHub empties the command and the count command again, so a switch
    to local and back leaves the row as it was (gate_timeout_s is the default 3600 both ways)."""
    if mode == GateMode.LOCAL:
        return ["project", "update", project, "--gate-cmd", LOCAL_GATE_CMD, "--gate-count-cmd", LOCAL_GATE_COUNT_CMD,
                "--gate-timeout-s", str(LOCAL_GATE_TIMEOUT_S)]
    return ["project", "update", project, "--gate-cmd", "", "--gate-count-cmd", ""]


def apply_gate_mode(factory_home, project, mode, env=None):
    """Switch `project` to `mode` through `bin/factory project update`. The caller has checked both against the DB."""
    return _run_factory(factory_home, gate_update_args(project, mode), env, "factory project update")


def gate_projects(con):
    """[{id, repo, cmd, mode, last}] for the Merge gate group: every project and its newest gate run (two queries).
    A database from before the local gate (no projects.gate_cmd or no gate_runs) has no rows here, as web/queries.py does."""
    if not has_column(con, "projects", "gate_cmd") or not has_column(con, "gate_runs", "id"):
        return []
    last = {r["project_id"]: dict(r) for r in con.execute(
        "SELECT g.id, g.project_id, g.status, g.head_sha, g.started, g.finished, g.created FROM gate_runs g "
        "JOIN (SELECT project_id, MAX(id) mid FROM gate_runs GROUP BY project_id) m ON g.id=m.mid")}
    return [{"id": p["id"], "repo": p["repo_path"] or "", "cmd": p["gate_cmd"] or "", "mode": gate_mode(p["gate_cmd"]),
             "last": last.get(p["id"])} for p in con.execute("SELECT id, repo_path, gate_cmd FROM projects ORDER BY id")]


def _shown(s, value):
    if s.kind == Kind.SWITCH:
        return Label.ON if value == ON else Label.OFF if value == OFF else value
    if s.kind == Kind.CHOICE:
        return dict(s.options).get(value, value)
    if s.kind == Kind.URL and not value:
        return "not set"
    return value


def data(ctx):
    have = dict(ctx.db.execute(f"SELECT key, value FROM config WHERE key IN ({','.join('?' * len(EDITABLE))})",
                               sorted(EDITABLE)).fetchall())
    dflt = ctx.defaults or {}
    groups = []
    for title, note, items in GROUPS:
        rows = []
        for s in items:
            default = str(dflt.get(s.key, ""))
            value = str(have.get(s.key, default))
            rows.append({"key": s.key, "label": s.label, "help": s.help, "kind": s.kind, "min": s.lo, "max": s.hi,
                         "options": [{"value": v, "label": lab} for v, lab in s.options or ()],
                         "value": value, "default": default, "is_default": s.key not in have or value == default})
        groups.append({"title": title, "note": note, "settings": rows})
    q = ctx.query or {}
    result = None
    if q.get(Q_SAVED) in EDITABLE:
        result = {"ok": True, "key": q[Q_SAVED], "msg": ""}
    elif q.get(Q_ERROR) in EDITABLE:
        result = {"ok": False, "key": q[Q_ERROR], "msg": (q.get(Q_MSG) or "")[:MSG_MAX]}
    projects = gate_projects(ctx.db)
    ids = {p["id"] for p in projects}
    gate_result = None
    if q.get(Q_GATE_SAVED) in ids:
        gate_result = {"ok": True, "project": q[Q_GATE_SAVED], "msg": ""}
    elif q.get(Q_GATE_ERROR) in ids:
        gate_result = {"ok": False, "project": q[Q_GATE_ERROR], "msg": (q.get(Q_MSG) or "")[:MSG_MAX]}
    return {"groups": groups, "editable": bool(getattr(ctx, "loopback", False)), "result": result,
            "projects": projects, "gate_result": gate_result}


_URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?")


def _control(s):
    if s["kind"] == Kind.SWITCH:
        return el("select", el("option", "On", value=ON, selected=s["value"] == ON),
                  el("option", "Off", value=OFF, selected=s["value"] != ON),
                  name="value", class_="set-input", aria_label=s["label"])
    if s["kind"] == Kind.CHOICE:
        return el("select", *[el("option", o["label"], value=o["value"], selected=s["value"] == o["value"])
                              for o in s["options"]], name="value", class_="set-input", aria_label=s["label"])
    if s["kind"] == Kind.URL:
        return el("input", type="url", name="value", value=s["value"], placeholder="http://localhost:4001/workspace/project", maxlength=str(VALUE_MAX),
                  required=True, class_="set-input", aria_label=s["label"])
    return el("input", type="number", name="value", value=s["value"], min=str(s["min"]), max=str(s["max"]), step="1",
              required=True, class_="set-input", aria_label=s["label"])


def _row(ctx, d, s):
    current = SETTINGS[s["key"]]
    value = el("span", _shown(current, s["value"]), class_="set-value")
    dflt = el("span", "default" if s["is_default"] else f"default: {_shown(current, s['default'])}", class_="set-default")
    if d["editable"]:
        ctl = el("form", el("input", type="hidden", name="token", value=getattr(ctx, "form_token", "") or ""),
                 el("input", type="hidden", name="key", value=s["key"]), _control(s),
                 el("button", "Save", type="submit", class_="set-btn"),
                 method="post", action="/settings", class_="set-form")
    else:
        if s["kind"] == Kind.SWITCH:
            example = OFF if s["value"] == ON else ON
        elif s["kind"] == Kind.CHOICE:   # the first value it is not set to
            example = next(o["value"] for o in s["options"] if o["value"] != s["value"])
        else:
            example = s["value"]
        ctl = el("code", f"factory config {s['key']} {example}", class_="set-cmd")
    note = None
    r = d["result"]
    if r and r["key"] == s["key"]:
        note = el("p", "Saved." if r["ok"] else f"Not changed: {r['msg'] or 'refused'}",
                  class_="set-note set-note--ok" if r["ok"] else "set-note set-note--bad", role="status")
    return el("div", el("div", el("span", s["label"], class_="set-name"), el("code", s["key"], class_="set-key"),
                        el("p", s["help"], class_="set-help"), class_="set-text"),
              el("div", el("div", value, " ", dflt, class_="set-now"), ctl, note, class_="set-ctl"),
              class_="set-row", id=f"set-{s['key']}")


def _last_run(r):
    """One line on a project's newest gate run (HM-53)."""
    if not r:
        return "Last local run: no run yet"
    start, end = parse_ts(r["started"]), parse_ts(r["finished"])
    took = f", {int((end - start).total_seconds())} s" if start and end else ""
    at = start or parse_ts(r["created"])
    when = at.astimezone().strftime("%m-%d %H:%M") if at else "?"
    return f"Last local run: #{r['id']} {r['status']}{took}, started {when}, head {(r['head_sha'] or '?')[:8]}"


def _gate_row(ctx, d, p):
    """One project of the Merge gate group: what clears a change, a switch (not for a custom command), the last run."""
    value = el("span", GATE_MODE_LABELS[p["mode"]], class_="set-value")
    if p["mode"] == GateMode.CUSTOM:
        ctl = el("p", "Read-only here: a custom gate command (", el("code", p["cmd"], class_="set-cmd"),
                 "); change it with factory project update.", class_="set-help")
    elif d["editable"]:
        ctl = el("form", el("input", type="hidden", name="token", value=getattr(ctx, "form_token", "") or ""),
                 el("input", type="hidden", name="project", value=p["id"]),
                 el("select", *[el("option", GATE_MODE_LABELS[m], value=m, selected=p["mode"] == m) for m in GATE_CHOICES],
                    name="mode", class_="set-input", aria_label=f"What clears a change in {p['id']}"),
                 el("button", "Save", type="submit", class_="set-btn"), method="post", action=GATE_PATH, class_="set-form")
    else:
        other = GateMode.LOCAL if p["mode"] == GateMode.GITHUB else GateMode.GITHUB
        ctl = el("code", " ".join(a if a and " " not in a else f"'{a}'" for a in ["factory", *gate_update_args(p["id"], other)]),
                 class_="set-cmd")
    note = None
    r = d["gate_result"]
    if r and r["project"] == p["id"]:
        note = el("p", "Saved." if r["ok"] else f"Not changed: {r['msg'] or 'refused'}",
                  class_="set-note set-note--ok" if r["ok"] else "set-note set-note--bad", role="status")
    return el("div", el("div", el("span", f"What clears a change in {p['id']}", class_="set-name"),
                        el("code", p["repo"] or p["id"], class_="set-key"),
                        el("p", _last_run(p["last"]), class_="set-help"), class_="set-text"),
              el("div", el("div", value, class_="set-now"), ctl, note, class_="set-ctl"),
              class_="set-row", id=f"gate-{p['id']}")


def render(ctx, d):
    intro = (el("p", "Changes run factory config on this machine and are logged as config events.", class_="set-intro")
             if d["editable"] else
             el("p", "Read-only: settings can be changed here only when factory serve is bound to 127.0.0.1. "
                     "Run the command shown instead.", class_="set-intro"))

    def rows(g):
        extra = [_gate_row(ctx, d, p) for p in d["projects"]] if g["title"] == MERGE_GATE_GROUP else []
        return [*extra, *[_row(ctx, d, s) for s in g["settings"]]]

    return el("div", intro, *[section(g["title"], el("p", g["note"], class_="set-help"), *rows(g)) for g in d["groups"]],
              class_="settings")
