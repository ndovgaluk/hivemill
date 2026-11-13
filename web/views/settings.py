"""Settings page (HM-1): curated global factory settings, in groups.

Editable only while `factory serve` is bound to a loopback address: then each setting has a small form that POSTs to
/settings, and the server runs `bin/factory config <key> <value>`, so the CLI's validation, role check and `config set`
event stay the only write path (the server itself keeps its read-only DB connection). On a LAN bind the page is
read-only and shows the command instead.
"""
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

from web.components import section
from web.html import el

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
    )),
)
SETTINGS = {s.key: s for _, _, items in GROUPS for s in items}
EDITABLE = frozenset(SETTINGS)


def valid_value(key, value):
    """True when `value` is one the page offers for `key`. An integer's range stays with the CLI, which names it."""
    s = SETTINGS[key]
    if s.kind == Kind.CHOICE:
        return value in dict(s.options)
    if s.kind == Kind.SWITCH:
        return value in (ON, OFF)
    return value.isascii() and value.isdigit()

# query parameters of the redirect after a change (server: Handler._settings_post)
Q_SAVED, Q_ERROR, Q_MSG = "saved", "error", "msg"


def apply_change(factory_home, key, value, env=None):
    """Run `bin/factory config <key> <value>`; returns (ok, message). The caller has checked `key` is in EDITABLE."""
    cmd = [sys.executable, str(ROOT / "bin" / "factory"), "config", key, value]
    run_env = dict(os.environ if env is None else env)
    if factory_home:
        run_env["FACTORY_HOME"] = str(factory_home)
    try:
        r = subprocess.run(cmd, env=run_env, capture_output=True, text=True, timeout=CONFIG_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"factory config could not run: {e}"[:MSG_MAX]
    if r.returncode == 0:
        return True, ""
    last = (r.stderr.strip().splitlines() or [f"factory config exited {r.returncode}"])[-1]
    return False, last.removeprefix("factory: ")[:MSG_MAX]


def _shown(s, value):
    if s.kind == Kind.SWITCH:
        return Label.ON if value == ON else Label.OFF if value == OFF else value
    if s.kind == Kind.CHOICE:
        return dict(s.options).get(value, value)
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
    return {"groups": groups, "editable": bool(getattr(ctx, "loopback", False)), "result": result}


def _control(s):
    if s["kind"] == Kind.SWITCH:
        return el("select", el("option", "On", value=ON, selected=s["value"] == ON),
                  el("option", "Off", value=OFF, selected=s["value"] != ON),
                  name="value", class_="set-input", aria_label=s["label"])
    if s["kind"] == Kind.CHOICE:
        return el("select", *[el("option", o["label"], value=o["value"], selected=s["value"] == o["value"])
                              for o in s["options"]], name="value", class_="set-input", aria_label=s["label"])
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


def render(ctx, d):
    intro = (el("p", "Changes run factory config on this machine and are logged as config events.", class_="set-intro")
             if d["editable"] else
             el("p", "Read-only: settings can be changed here only when factory serve is bound to 127.0.0.1. "
                     "Run the command shown instead.", class_="set-intro"))
    return el("div", intro, *[section(g["title"], el("p", g["note"], class_="set-help"),
                                      *[_row(ctx, d, s) for s in g["settings"]]) for g in d["groups"]],
              class_="settings")
