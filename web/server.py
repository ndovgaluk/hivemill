"""HTTP server for the factory web UI (stdlib only, GET/HEAD, LAN bind, Host allowlist).

Opens the factory DB (db_path: a path, or a callable resolved per request) only through web.db (read-only URI, one connection per request).
The one write path is POST /settings (HM-1): accepted only on a loopback bind, same Origin, with the per-process form
token and a curated key; it runs `bin/factory config <key> <value>`, so the CLI validates, checks the role and logs it.
"""
import datetime as dt
import hmac
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from web import db as wdb
from web import flow, flow_findings, flowcost
from web import queries
from web.html import page
from web.tokens import TokenIndex
from web.views import ROUTES
from web.views import goal_control as goal_control_view  # HM-42
from web.views import halt as halt_view  # HM-44
from web.views import settings as settings_view

STATIC = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".js": "text/javascript; charset=utf-8",
                ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2"}
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
# HM-1: a page with forms (view.FORMS) may submit to this origin only, and needs a same-origin referrer policy:
# with no-referrer a browser sends `Origin: null` on a form POST, and the Origin check below would refuse it
CSP_FORMS = CSP.replace("form-action 'none'", "form-action 'self'")
REFERRER = "no-referrer"
REFERRER_FORMS = "same-origin"
SETTINGS_PATH = "/settings"
FORM_TYPE = "application/x-www-form-urlencoded"
MAX_FORM_BYTES = 1024
MAX_CONCURRENT = 8
REQUEST_TIMEOUT_S = 10
_ID_RE = re.compile(r"^/(goal|task)/([A-Z]-\d+)$")
_FLOW_RE = re.compile(r"^/api/flow/(goal|task)/([A-Z]-\d+)\.json$")   # DVDG-553
JSON_TYPE = "application/json"
STATIC_CACHE = "max-age=3600"
FLOW_CACHE = "no-cache"            # revalidate on every load
FLOW_STATIC_PREFIX = "flow/"
_STATIC_NAME_RE = re.compile(r"^(?:fonts/|flow/)?[\w][\w.-]*$")  # one level: static/fonts/, static/flow/ (DVDG-554 bundle)
RELOAD_INTERVAL_S = 60     # FACTORY_SERVE_RELOAD_INTERVAL overrides it (tests)
SHOW_TEXT_KEY = "serve_show_text"   # config key (bin/factory_cli.py DEFAULT_CONFIG), read per request
ROOT = Path(__file__).resolve().parent.parent
# callables a view may append at import; each runs once in a daemon thread when the server starts
background = []


class Ctx:
    """What a view gets: a per-request read-only connection plus injected helpers."""

    def __init__(self, db, tokens, usage_fn, mem_fn, defaults, now, factory_home=None, query=None, show_text=False,
                 loopback=False, form_token=None):
        self.db, self.tokens, self.usage_fn, self.mem_fn = db, tokens, usage_fn, mem_fn
        self.defaults, self.now, self.factory_home = defaults, now, factory_home
        self.query = query or {}    # str -> first value of the query string; views validate what they use
        self.show_text = show_text  # DVDG-544: instruction text may be shown (see show_text_allowed)
        self.loopback, self.form_token = loopback, form_token   # HM-1: settings forms only on a loopback bind


def is_loopback(bind):
    try:
        return ipaddress.ip_address(bind).is_loopback
    except ValueError:
        return False


def show_text_allowed(bind, setting):
    """Instruction text (message bodies, spec, acceptance, verdict summaries) is shown only when the owner set
    serve_show_text=1 AND the server listens on a loopback address: an unauthenticated UI must not serve it on a LAN."""
    return is_loopback(bind) and (setting or "").strip() == "1"


def _refuse(msg):
    print(f"factory serve: {msg}", file=sys.stderr)
    raise SystemExit(2)


def pick_bind(explicit=None):
    """Bind address: `explicit`, else the source address of the default route (UDP connect, no packet sent).
    Refuses unspecified, multicast and non-private addresses; loopback is allowed."""
    addr = explicit
    if not addr:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.0.2.1", 9))
            addr = s.getsockname()[0]
        except OSError as e:
            _refuse(f"cannot find the LAN address ({e}); pass --bind ADDR")
        finally:
            s.close()
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        _refuse(f"refusing to bind {addr!r}: not an IP address")
    if ip.is_unspecified or ip.is_multicast:
        _refuse(f"refusing to bind {addr}: must be one private LAN address, not a wildcard or multicast")
    if not (ip.is_private or ip.is_loopback):
        _refuse(f"refusing to bind {addr}: not a private (LAN) address")
    return str(ip)


def _host_allowed(bind, port, hostnames):
    bare = f"[{bind}]" if ":" in bind else bind
    ok = {f"{bare}:{port}"}
    names = [n.strip().lower() for n in hostnames if n.strip()]
    ok.update(f"{n}:{port}" for n in names)
    if port == 80:
        ok.add(bare)
        ok.update(names)
    return ok


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "factory-web"
    sys_version = ""
    timeout = REQUEST_TIMEOUT_S

    # ── plumbing ──
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=None, cache="no-store", forms=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP_FORMS if forms else CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", REFERRER_FORMS if forms else REFERRER)
        self.send_header("Cache-Control", cache)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, code, msg, extra=None):
        self._send(code, f"{code} {msg}\n", "text/plain; charset=utf-8", extra)

    def _dispatch(self):
        app = self.server.app
        settings_post = self.command == "POST" and urlsplit(self.path).path in (SETTINGS_PATH, settings_view.GATE_PATH,
                                                                                 halt_view.HALT_PATH, halt_view.START_PATH,
                                                                                 goal_control_view.PATH)
        if self.command not in ("GET", "HEAD") and not settings_post:
            return self._error(405, "method not allowed", {"Allow": "GET, HEAD"})
        if not app.sem.acquire(blocking=False):
            return self._error(503, "busy", {"Retry-After": "1"})
        try:
            host = (self.headers.get("Host") or "").strip().lower()
            if host not in app.hosts:
                return self._error(421, "misdirected request")
            parts = urlsplit(self.path)
            try:
                self.query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True, max_num_fields=20).items()}
            except ValueError:  # too many fields: ignore the query string
                self.query = {}
            self._path = parts.path
            if settings_post:
                if parts.path == goal_control_view.PATH:
                    return self._goal_control_post(app, host)
                if parts.path in (halt_view.HALT_PATH, halt_view.START_PATH):
                    return self._halt_post(app, host, parts.path)
                return self._gate_post(app, host) if parts.path == settings_view.GATE_PATH else self._settings_post(app, host)
            self._route(parts.path)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            raise
        except Exception:  # noqa: BLE001 — never leak a traceback to the client
            traceback.print_exc()
            try:
                self._send(500, page("Error", "<p class=\"empty\">Something went wrong.</p>", "", refresh=False))
            except OSError:
                pass
        finally:
            app.sem.release()

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = _dispatch

    # ── routing ──
    def _route(self, path):
        app = self.server.app
        if path == "/healthz":
            return self._healthz(app)
        if path.startswith("/static/"):
            return self._static(unquote(path[len("/static/"):]))
        m = _FLOW_RE.match(path)
        if m:
            return self._flow(m.group(1), m.group(2))
        if path.startswith("/api/") and path.endswith(".json"):
            name = path[len("/api/"):-len(".json")]
            route = "/" if name == "home" else f"/{name}"
            view = ROUTES.get(route) if "<" not in route else None
            if view is None:
                return self._error(404, "not found")
            return self._view(view, route, {}, as_json=True)
        view, params, active = ROUTES.get(path), {}, path
        if view is None:
            m = _ID_RE.match(path)
            if m:
                view, params, active = ROUTES.get(f"/{m.group(1)}/<id>"), {"id": m.group(2)}, f"/{m.group(1)}s"
        if view is None:
            return self._error(404, "not found")
        self._view(view, getattr(view, "NAV", active), params)   # a page outside the menu names the item it sits under

    def _view(self, view, active, params, as_json=False):
        app = self.server.app
        with wdb.reader(app.current_db()) as con:
            setting = con.execute("SELECT value FROM config WHERE key=?", (SHOW_TEXT_KEY,)).fetchone()
            ctx = Ctx(con, app.tokens, app.usage_fn, app.mem_fn, app.defaults, dt.datetime.now().astimezone(), app.factory_home,
                      getattr(self, "query", {}), show_text=show_text_allowed(app.bind, setting[0] if setting else None),
                      loopback=app.loopback, form_token=None if as_json else app.form_token)
            data = view.data(ctx, **params)
            if as_json:
                body, ctype = json.dumps(data, default=str), "application/json"
            else:
                shell = {**queries.shell_status(con, app.usage_fn() if app.usage_fn else None, app.defaults,
                                                 mem=app.mem_fn() if app.mem_fn else None, now=ctx.now,
                                                 org=queries.org_param(ctx.query)), "now": ctx.now,
                         "loopback": app.loopback}   # HM-44: the Urgent stop button only on a loopback bind
                # DVDG-561: the goal and task pages refresh their flow data themselves; no 60 s full-page reload there
                body = page(getattr(view, "TITLE", active), view.render(ctx, data), active, shell=shell,
                            refresh=getattr(view, "REFRESH", True),
                            org=queries.org_param(ctx.query), path=getattr(self, "_path", None), query=ctx.query)
                ctype = "text/html; charset=utf-8"
        self._send(200, body, ctype, forms=not as_json and getattr(view, "FORMS", False))  # reader closed before the write

    def _flow(self, scope, oid):
        """DVDG-553: the flow debugger's JSON for one goal or task; 404 JSON for an unknown id."""
        app = self.server.app
        with wdb.reader(app.current_db()) as con:
            setting = con.execute("SELECT value FROM config WHERE key=?", (SHOW_TEXT_KEY,)).fetchone()
            now = dt.datetime.now().astimezone()
            data = flow.build(con, scope, oid, now, show_text_allowed(app.bind, setting[0] if setting else None))
            if data is not None:   # DVDG-555: tokens and cost per box and step, from the logs the token index knows
                index = getattr(app.tokens, "__self__", None)
                flowcost.fill(data, con, flowcost.Usage(app.tokens() if app.tokens else {},
                                                        index if isinstance(index, TokenIndex) else None))
                flow_findings.attach(data, con, now)   # DVDG-560
        if data is None:
            return self._send(404, json.dumps({"error": "not found", "scope": scope, "id": oid}), JSON_TYPE)
        self._send(200, json.dumps(data, default=str), JSON_TYPE)

    def _checked_form(self, app, host):
        """The Settings page's write guard (HM-1), shared by both POST paths: loopback bind, same Origin, a form content
        type, a size limit and the per-process form token. Returns the form, or None after sending the refusal."""
        if not app.loopback:
            return self._error(403, "settings can be changed only when factory serve is bound to a loopback address")
        if (self.headers.get("Origin") or "") != f"http://{host}":
            return self._error(403, "cross-origin or missing Origin")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != FORM_TYPE:
            return self._error(400, "expected a form")
        try:
            size = int(self.headers.get("Content-Length") or "")
        except ValueError:
            return self._error(400, "missing length")
        if size < 0 or size > MAX_FORM_BYTES:
            return self._error(413, "form too large")
        try:
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True,
                                                 max_num_fields=5).items()}
        except (UnicodeDecodeError, ValueError):
            return self._error(400, "bad form")
        if not hmac.compare_digest(form.get("token", ""), app.form_token):
            return self._error(403, "form expired: reload the page")
        return form

    def _gate_post(self, app, host):
        """HM-53: switch one project's merge gate between GitHub CI and the local test run. Same guard as _settings_post;
        an unknown project or mode, or a project with a custom gate command, is refused before any subprocess runs."""
        form = self._checked_form(app, host)
        if form is None:
            return None
        project, mode = form.get("project", ""), form.get("mode", "")
        if mode not in settings_view.GATE_CHOICES or not project or len(project) > settings_view.PROJECT_MAX:
            return self._error(400, "bad project or mode")
        with wdb.reader(app.current_db()) as con:
            row = con.execute("SELECT gate_cmd FROM projects WHERE id=?", (project,)).fetchone()
        if row is None:
            return self._error(400, "no such project")
        if settings_view.gate_mode(row["gate_cmd"]) == settings_view.GateMode.CUSTOM:
            return self._error(400, "a custom gate command is changed with factory project update, not here")
        ok, msg = settings_view.apply_gate_mode(app.factory_home, project, mode, env=app.config_env)
        target = (f"{SETTINGS_PATH}?{settings_view.Q_GATE_SAVED}={quote(project)}" if ok else
                  f"{SETTINGS_PATH}?{settings_view.Q_GATE_ERROR}={quote(project)}&{settings_view.Q_MSG}={quote(msg)}")
        self._send(303, "", "text/plain; charset=utf-8", {"Location": f"{target}#gate-{quote(project)}"})

    def _goal_control_post(self, app, host):
        """HM-42: Pause, Resume or Stop one goal, behind the Settings guard; an unknown action or a malformed goal id is
        refused before anything runs. The CLI checks the role and the goal's state; its last line comes back."""
        form = self._checked_form(app, host)
        if form is None:
            return None
        goal, action = form.get("goal", ""), form.get("action", "")
        if action not in goal_control_view.ACTIONS or not goal_control_view.GOAL_RE.match(goal):
            return self._error(400, "bad goal or action")
        reason = form.get("reason", "").strip()[:goal_control_view.REASON_MAX] or f"owner: {action} (dashboard)"
        ok, msg = goal_control_view.run(app.factory_home, goal, action, reason, env=app.config_env)
        q = "done" if ok else "msg"
        self._send(303, "", "text/plain; charset=utf-8",
                   {"Location": f"/goal/{goal}?ctl={action}&{q}={quote(msg or action)}"})

    def _halt_post(self, app, host, path):
        """HM-44: Urgent stop (`factory halt --reason`) or Start again (`factory start`), behind the same guard as the
        Settings forms (loopback bind, same Origin, form token). The CLI checks the owner role and does the work; its
        last line comes back on the page."""
        form = self._checked_form(app, host)
        if form is None:
            return None
        reason = form.get("reason", "").strip()[:halt_view.REASON_MAX] or halt_view.DEFAULT_REASON
        args = ["halt", "--reason", reason] if path == halt_view.HALT_PATH else ["start", "--reason", "Start again (dashboard)"]
        ok, msg = halt_view.run(app.factory_home, args, env=app.config_env)
        q = halt_view.Q_DONE if ok else halt_view.Q_MSG
        what = "halt" if path == halt_view.HALT_PATH else "start"
        self._send(303, "", "text/plain; charset=utf-8",
                   {"Location": f"{halt_view.HALT_PATH}?{halt_view.Q_WHAT}={what}&{q}={quote(msg or what)}"})

    def _settings_post(self, app, host):
        """HM-1: change one curated setting. Every check refuses on its own status; nothing is written unless all pass,
        and the write itself is `bin/factory config` (validation, role check, event)."""
        form = self._checked_form(app, host)
        if form is None:
            return None
        key, value = form.get("key", ""), form.get("value", "").strip()
        if key not in settings_view.EDITABLE:
            return self._error(400, "not an editable setting")
        if not value or len(value) > settings_view.VALUE_MAX or not settings_view.valid_value(key, value):
            return self._error(400, "bad value")
        ok, msg = settings_view.apply_change(app.factory_home, key, value, env=app.config_env)
        target = (f"{SETTINGS_PATH}?{settings_view.Q_SAVED}={quote(key)}" if ok else
                  f"{SETTINGS_PATH}?{settings_view.Q_ERROR}={quote(key)}&{settings_view.Q_MSG}={quote(msg)}")
        self._send(303, "", "text/plain; charset=utf-8", {"Location": f"{target}#set-{key}"})

    def _healthz(self, app):
        try:
            age = max(0, int(time.time() - os.stat(app.current_db()).st_mtime))
        except OSError:
            return self._send(503, "db missing\n", "text/plain; charset=utf-8")
        self._send(200, f"ok\ndb_mtime_age_s={age}\n", "text/plain; charset=utf-8")

    def _static(self, name):
        if not _STATIC_NAME_RE.match(name):
            return self._error(404, "not found")
        f = (STATIC / name).resolve()
        ctype = STATIC_TYPES.get(f.suffix)
        if STATIC.resolve() not in f.parents or ctype is None or not f.is_file():
            return self._error(404, "not found")
        # the flow bundle is rebuilt in place under a fixed name and must match the JSON contract of the same checkout:
        # a copy cached for an hour breaks the page after an update (HM-13)
        self._send(200, f.read_bytes(), ctype, cache=FLOW_CACHE if name.startswith(FLOW_STATIC_PREFIX) else STATIC_CACHE)


class _App:
    def __init__(self, db_path, bind, port, hostnames, tokens, usage_fn, mem_fn, defaults, factory_home):
        self.db_path, self.tokens, self.usage_fn, self.mem_fn = db_path, tokens, usage_fn, mem_fn
        self.defaults, self.factory_home, self.bind = defaults, factory_home, bind
        self.hosts = _host_allowed(bind, port, hostnames)
        self.loopback = is_loopback(bind)             # HM-1: settings are editable only then
        self.form_token = secrets.token_urlsafe(32)   # per process: a re-exec on code change invalidates open forms
        self.config_env = None                        # env for `bin/factory config` (None = this process's; tests set it)
        self.sem = threading.BoundedSemaphore(MAX_CONCURRENT)

    def current_db(self):
        """The DB path for this request: db_path may be a callable, so a layout migration under a running server is
        picked up on the next request (never a stale, renamed file)."""
        return self.db_path() if callable(self.db_path) else self.db_path


def make_server(db_path, bind, port, hostnames=(), tokens=None, usage_fn=None, mem_fn=None, defaults=None,
                factory_home=None):
    """Bound but not serving. port 0 picks a free port; the Host allowlist uses the port actually bound."""
    cls = _Server
    if ":" in bind:
        cls = type("_Server6", (_Server,), {"address_family": socket.AF_INET6})
    httpd = cls((bind, port), Handler)
    httpd.app = _App(db_path, bind, httpd.server_address[1], hostnames, tokens, usage_fn, mem_fn, defaults, factory_home)
    return httpd


def code_signature(root=ROOT):
    """(mtime_ns, size) of every web/**/*.py, scout/**/*.py (bin/factory_cli.py imports it) and bin/factory_cli.py under root:
    what the running process imported."""
    sig = {}
    for f in [*sorted((root / "web").rglob("*.py")), *sorted((root / "scout").rglob("*.py")), root / "bin" / "factory_cli.py"]:
        try:
            st = f.stat()
        except OSError:
            continue
        sig[str(f)] = (st.st_mtime_ns, st.st_size)
    return sig


def import_check(root=ROOT):
    """None if the code under root imports and bin/factory compiles in a fresh interpreter, else a one-line reason."""
    code = "import web.server; compile(open('bin/factory_cli.py').read(), 'bin/factory_cli.py', 'exec')"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"import check could not run: {e}"
    if r.returncode:
        return (r.stderr.strip().splitlines() or ["import failed"])[-1]
    return None


def watch_code(httpd, state, interval, seen, root=ROOT):
    """Daemon loop: when the code changed and still imports, flag a reload and stop the accept loop. A broken
    change logs one error line (stderr -> journal; serve never writes the DB) and keeps the old code; the next
    change is checked again."""
    while True:
        time.sleep(interval)
        now = code_signature(root)
        if now == seen:
            continue
        seen = now
        err = import_check(root)
        if err:
            print(f"factory serve: error: code changed but does not import, still serving the old code: {err}",
                  file=sys.stderr, flush=True)
            continue
        state["reload"] = True
        httpd.shutdown()
        return


def watch_ttl(httpd, state, seconds, sleep=time.sleep):
    """Daemon: after `seconds`, flag the TTL and stop the accept loop (the process then exits by itself)."""
    sleep(seconds)
    state["ttl"] = True
    httpd.shutdown()


def run(db_path, bind=None, port=8765, hostnames=(), usage_fn=None, mem_fn=None, defaults=None, factory_home=None,
        ttl_minutes=0):
    try:
        os.nice(10)
    except OSError:
        pass
    bind = pick_bind(bind)
    index = TokenIndex()
    index.start_background(60)
    try:
        httpd = make_server(db_path, bind, port, hostnames, index.snapshot, usage_fn, mem_fn, defaults, factory_home)
    except OSError as e:
        _refuse(f"cannot listen on {bind}:{port}: {e}")
    for fn in background:
        threading.Thread(target=fn, daemon=True).start()

    def stop(signum, frame):
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    state = {"reload": False, "ttl": False}
    if ttl_minutes and ttl_minutes > 0:
        threading.Thread(target=watch_ttl, args=(httpd, state, ttl_minutes * 60), daemon=True).start()
    try:
        interval = float(os.environ.get("FACTORY_SERVE_RELOAD_INTERVAL") or RELOAD_INTERVAL_S)
    except ValueError:
        interval = RELOAD_INTERVAL_S
    threading.Thread(target=watch_code, args=(httpd, state, max(interval, 0.1), code_signature()), daemon=True).start()
    shown = f"[{bind}]" if ":" in bind else bind
    print(f"factory serve: http://{shown}:{httpd.server_address[1]}/ (read-only, LAN only, no auth)", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()   # joins in-flight requests: the current request finishes first
    if state["ttl"]:
        print(f"factory serve: ttl of {ttl_minutes} min reached, exiting", flush=True)
    if state["reload"]:
        for _ in range(MAX_CONCURRENT):   # handler threads are daemons: wait for the in-flight requests to answer
            if not httpd.app.sem.acquire(timeout=REQUEST_TIMEOUT_S):
                break
        print("factory serve: code changed, re-executing", flush=True)
        os.execv(sys.executable, sys.orig_argv)
