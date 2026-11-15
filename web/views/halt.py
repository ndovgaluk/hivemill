"""HM-44: the Urgent stop page. GET shows what a halt does (with how many agents run now) and the confirm form, or,
while the factory is halted, since when, why, how many agents still close, and the Start again form. The two forms post
to /halt and /start (web/server.py _halt_post), which run `factory halt` and `factory start`."""
from web import queries
from web.html import el
from web.views import settings as settings_view

TITLE = "Urgent stop"
FORMS = True             # this page holds the two forms (form-action 'self'); every other page only links here
NAV = "/settings"        # not in the menu itself: Settings (under System) is marked current
HALT_PATH, START_PATH = "/halt", "/start"
Q_WHAT, Q_DONE, Q_MSG = "what", "done", "msg"
REASON_MAX = 200
DEFAULT_REASON = "Urgent stop from the dashboard"
RUNNING = ("queued", "starting", "live")
WHAT_HALT = ("Every agent is stopped: workers, leads, the director and the boss (queued starts are cancelled).",
             "Nothing new starts and nothing merges until Start again: no spawn, wake, nudge, relaunch, review, judge, "
             "merge or workflow-engine step.",
             "The tick keeps closing agents that did not close at once, and nothing else.",
             "Nothing is deleted: goals, tasks, pull requests, branches and worktrees stay as they are.")


def run(factory_home, args, env=None):
    """`bin/factory halt|start ...` as a subprocess (the CLI checks the owner role); (ok, last line)."""
    return settings_view._run_factory(factory_home, args, env, f"factory {args[0]}")


def data(ctx):
    n = dict(tuple(r) for r in ctx.db.execute("SELECT status, COUNT(*) FROM agents GROUP BY status"))
    return {"halt": queries.halt_status(ctx.db), "running": sum(n.get(s, 0) for s in RUNNING),
            "editable": bool(ctx.loopback), "what": ctx.query.get(Q_WHAT), "done": ctx.query.get(Q_DONE),
            "msg": ctx.query.get(Q_MSG)}


def _form(ctx, path, label, *fields):
    return el("form", el("input", type="hidden", name="token", value=ctx.form_token or ""), *fields,
              el("button", label, type="submit", class_="set-btn halt-go" if path == HALT_PATH else "set-btn"),
              method="post", action=path, class_="set-form")


def render(ctx, d):
    out = []
    if d["msg"]:
        out.append(el("p", d["msg"], class_="set-note set-note--bad", role="status"))
    elif d["done"]:
        out.append(el("p", d["done"], class_="set-note set-note--ok", role="status"))
    h = d["halt"]
    if h:
        out.append(el("p", f"The factory is halted since {h['since'] or 'an unknown time'}: {h['reason']}.",
                      class_="halt-state"))
        out.append(el("p", f"{h['closing']} agent(s) still closing; the tick retries them." if h["closing"]
                      else "Every agent is stopped.", class_="set-help"))
        out.append(el("p", "Start again clears the halt and brings the boss, the director and the leads back "
                           "(factory up). Goals and tasks keep the states they had.", class_="set-help"))
        out.append(_form(ctx, START_PATH, "Start again") if d["editable"] else el("code", "factory start", class_="set-cmd"))
    else:
        out.append(el("p", f"{d['running']} agent(s) are queued, starting or running now. An urgent stop:", class_="set-help"))
        out.append(el("ul", [el("li", w) for w in WHAT_HALT], class_="lrow-list"))
        out.append(_form(ctx, HALT_PATH, "Stop everything now",
                         el("input", type="text", name="reason", maxlength=str(REASON_MAX), placeholder="Reason (optional)",
                            aria_label="Reason", class_="set-input")) if d["editable"]
                   else el("code", "factory halt --reason \"...\"", class_="set-cmd"))
    return el("div", *out, class_="settings halt-page")
