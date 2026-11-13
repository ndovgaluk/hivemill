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


ON, OFF = "1", "0"
Setting = namedtuple("Setting", "key label help kind lo hi")
GROUPS = (
    ("Worktrees", "How coder tasks get their git worktree. Details: docs/worktree-reuse.md.", (
        Setting("worktree_reuse", "Reuse coder worktrees",
                "On: factory clean keeps a merged task's clean worktree in a pool and the next coder task of the same "
                "project reuses it (ignored files such as node_modules stay). Off: every coder task gets a fresh "
                "worktree, deleted after merge.", Kind.SWITCH, None, None),
        Setting("worktree_pool_max", "Free worktrees kept per project",
                "How many unused worktrees factory clean keeps per project while reuse is on.", Kind.INT, 0, 50),
    )),
)
EDITABLE = frozenset(s.key for _, _, items in GROUPS for s in items)

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
        return "On" if value == ON else "Off" if value == OFF else value
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
    return el("input", type="number", name="value", value=s["value"], min=str(s["min"]), max=str(s["max"]), step="1",
              required=True, class_="set-input", aria_label=s["label"])


def _row(ctx, d, s):
    current = next(x for _, _, items in GROUPS for x in items if x.key == s["key"])
    value = el("span", _shown(current, s["value"]), class_="set-value")
    dflt = el("span", "default" if s["is_default"] else f"default: {_shown(current, s['default'])}", class_="set-default")
    if d["editable"]:
        ctl = el("form", el("input", type="hidden", name="token", value=getattr(ctx, "form_token", "") or ""),
                 el("input", type="hidden", name="key", value=s["key"]), _control(s),
                 el("button", "Save", type="submit", class_="set-btn"),
                 method="post", action="/settings", class_="set-form")
    else:
        example = (OFF if s["value"] == ON else ON) if s["kind"] == Kind.SWITCH else s["value"]
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
