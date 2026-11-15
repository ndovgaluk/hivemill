"""HM-50: the flow debugger's diagram per workflow, and the read of the engine's own database.

A goal (or its factory task) ran under the old workflow (boss, director, lead, PM, coders, review gate, judge) or under a
story run of the workflow engine with workflow `simple`, `medium` or `huge` (`workflows/<name>.md`) and a CI mode
(`docs/workflow-engine.md`, "CI mode"). The old diagram lives in web/flow.py as before; the engine's diagrams are defined
here, one per workflow and CI mode, each with all of its participants. Steps the engine does not run yet are `planned`:
drawn dashed, with no sessions and no times (owner decisions on TSR story HM-50, 2026-11-15).

The engine keeps its runs in `<home>/db/workflow.db`, beside factory.db. It is opened read-only (URI mode=ro), never
created; a home without it, or a goal that is not a run in it, is the old workflow.
"""
import os
import sqlite3
from urllib.parse import quote

WORKFLOW_DB = "workflow.db"
WORKFLOW_DB_VERSION = 2   # go/internal/workflow/state.go UserVersion; another version is read as "unreadable"


class Kind:
    OLD, SIMPLE, MEDIUM, HUGE = "old", "simple", "medium", "huge"
    ENGINE = (SIMPLE, MEDIUM, HUGE)


class Ci:
    GITHUB, LOCAL, NONE = "github", "local", "none"
    ALL = (GITHUB, LOCAL, NONE)


class Origin:
    CHOSEN, GIVEN = "chosen", "given"
    EVENTS = {"workflow-chosen": CHOSEN, "workflow-given": GIVEN}   # factory events, entity 'workflow' (choose.go)


CI_TEXT = {Ci.GITHUB: "pull request, review gate, judge", Ci.LOCAL: "no PR, affected tests on this machine",
           Ci.NONE: "no PR, no tests"}
NOTE_PLANNED = "planned, not built"
NOTE_NO_TESTS = "no tests"
NOTE_UNREADABLE = "workflow.db unreadable"


class N:
    """Node ids of the engine diagrams. Those shared with the old diagram (boss, wait, the final review gate, judge,
    merged) keep the old ids, so the inspector, the cost fill and the findings treat them alike."""
    BOSS, ENGINE, ARCHITECT, BUILDER, CHILD_REVIEW = "boss", "engine", "architect", "builder", "child_review"
    BRANCH_QA, MERGE_QUEUE = "branch_qa", "merge_queue"
    PR, GATE, REVIEWER, QA, JUDGE, MAIN = "pr", "gate", "reviewer", "qa", "judge", "main"
    TESTS, LAND, DONE, WAIT = "tests", "land", "done", "wait"


class E:
    """Edge ids of the engine diagrams."""
    BOSS_ENGINE, ENGINE_BUILDER, ENGINE_ARCHITECT, ARCHITECT_BUILDER = "be", "eb", "ea", "ab"
    BUILD_REVIEW, CHANGES, NON_CONVERGENCE = "br", "rb", "ra"
    REVIEW_QA, QA_QUEUE, QUEUE_FINISH, REVIEW_FINISH = "rq", "qm", "mf", "rf"
    PR_GATE, GATE_JUDGE, JUDGE_MAIN, MAIN_DONE, GATE_REWORK = "pg", "gj", "jm", "md", "fr"
    TESTS_LAND, TESTS_RED, LAND_DONE = "tl", "tb", "ld"


class Route:
    """How an engine edge is drawn (geometry() below turns it into points; the flow app only draws them)."""
    H = "h"             # same row, left to right, side to side
    V = "v"             # same column, straight up or down
    GAP_TOP = "gap_top"  # from the source's bottom into the gap above the target row, across, down into its top
    LOOP_UNDER = "loop_under"  # back to the left neighbour: under both boxes, from bottom to bottom
    SKIP_UNDER = "skip_under"  # forward past the boxes between: under them, up into the target's bottom
    BACK_UNDER = "back_under"  # back to the builder from further right: low under the row, up into its bottom


class Def:
    """One diagram: nodes (id, label, col, row, planned, note), groups (id, label, members), edges (id, from, tos, label,
    planned, route), lanes (id, node, label), and the ids build() needs for its own rules."""

    def __init__(self, kind, ci, nodes, groups, edges, lanes, work, spec_from, spec_edge, rework_edge, review_edge,
                 gate_nodes, verdict_node, merged, judge_edge, merge_edge, workers):
        self.kind, self.ci = kind, ci
        self.nodes, self.groups, self.edges, self.lanes = nodes, groups, edges, lanes
        self.work, self.spec_from, self.spec_edge = work, spec_from, spec_edge
        self.rework_edge, self.review_edge = rework_edge, review_edge
        self.gate_nodes, self.verdict_node, self.merged = gate_nodes, verdict_node, merged
        self.judge_edge, self.merge_edge, self.workers = judge_edge, merge_edge, workers
        self.edge_of = edge_index(edges, gate_nodes, groups)
        self.lane_node = {lane: node for lane, node, _ in lanes}
        self.node_lane = {node: lane for lane, node, _ in lanes}
        self.planned = {nid for nid, _, _, _, planned, _ in nodes if planned}


def edge_index(edges, gate_nodes=(), groups=()):
    """(from node, to node) -> (edge id, dir) for every drawn edge, both ways; an edge from or to a group also matches
    each of its members. A pair that is an edge of its own the other way keeps that edge."""
    members = {gid: m for gid, _, m in groups}
    out, back = {}, {}
    for eid, frm, tos, *_ in edges:
        for f in (frm, *members.get(frm, ())):
            for t in tos:
                for tt in (t, *members.get(t, ())):
                    out[(f, tt)] = (eid, 1)
                    back.setdefault((tt, f), (eid, -1))
    return {**back, **out}


def _engine(kind, ci):
    """The diagram of engine workflow `kind` finishing in CI mode `ci`."""
    architect = kind in (Kind.MEDIUM, Kind.HUGE)
    huge = kind == Kind.HUGE
    nodes = [(N.BOSS, "Boss", 0, 0, False, None), (N.ENGINE, "Engine", 1, 0, False, None)]
    if architect:
        nodes.append((N.ARCHITECT, "Architect", 2, 0, True, NOTE_PLANNED))
    nodes += [(N.BUILDER, "Builder", 1, 1, False, None), (N.CHILD_REVIEW, "Reviewer", 2, 1, False, "per child")]
    edges = [(E.BOSS_ENGINE, N.BOSS, (N.ENGINE,), "start", False, Route.H),
             (E.ENGINE_BUILDER, N.ENGINE, (N.BUILDER,), "kickoff", False, Route.V)]
    if architect:
        edges += [(E.ENGINE_ARCHITECT, N.ENGINE, (N.ARCHITECT,), "design", True, Route.H),
                  (E.ARCHITECT_BUILDER, N.ARCHITECT, (N.BUILDER,), "frozen design", True, Route.GAP_TOP)]
    edges += [(E.BUILD_REVIEW, N.BUILDER, (N.CHILD_REVIEW,), "in review", False, Route.H),
              (E.CHANGES, N.CHILD_REVIEW, (N.BUILDER,), "changes", False, Route.LOOP_UNDER)]
    if huge:
        nodes += [(N.BRANCH_QA, "QA", 3, 1, True, NOTE_PLANNED + ": the whole branch"),
                  (N.MERGE_QUEUE, "Merge queue", 4, 1, True, NOTE_PLANNED)]
        edges += [(E.NON_CONVERGENCE, N.CHILD_REVIEW, (N.ARCHITECT,), "non-convergence", True, Route.V),
                  (E.REVIEW_QA, N.CHILD_REVIEW, (N.BRANCH_QA,), "reviewed", True, Route.H),
                  (E.QA_QUEUE, N.BRANCH_QA, (N.MERGE_QUEUE,), "passed", True, Route.H)]
    groups = ()
    gate = ()
    verdict = {}
    lanes = [(N.BOSS, N.BOSS, "Boss"), (N.ENGINE, N.ENGINE, "Engine"), (N.BUILDER, N.BUILDER, "Builder"),
             (N.CHILD_REVIEW, N.CHILD_REVIEW, "Reviewer (child)")]
    c = max(col for _, _, col, row, _, _ in nodes if row == 1) + 1   # HM-50: the finish goes on along the work row
    if ci == Ci.GITHUB:
        first, merged = N.PR, N.MAIN
        nodes += [(N.PR, "Pull request", c, 1, False, None), (N.REVIEWER, "Reviewer", c + 1, 1, False, None),
                  (N.QA, "QA", c + 1, 2, False, None), (N.JUDGE, "Judge", c + 2, 1, False, None),
                  (N.MAIN, "Merged", c + 3, 1, False, None), (N.DONE, "Done", c + 4, 1, False, None)]
        gate = (N.REVIEWER, N.QA)
        groups = ((N.GATE, "Review gate", gate),)
        verdict = {"reviewer": N.REVIEWER, "qa": N.QA, "judge": N.JUDGE}
        finish = [(E.PR_GATE, N.PR, (N.GATE,), "review", False, Route.H),
                  (E.GATE_JUDGE, N.GATE, (N.JUDGE,), "verdict", False, Route.H),
                  (E.JUDGE_MAIN, N.JUDGE, (N.MAIN,), "merge", False, Route.H),
                  (E.MAIN_DONE, N.MAIN, (N.DONE,), "close", False, Route.H),
                  (E.GATE_REWORK, N.GATE, (N.BUILDER,), "rework", False, Route.BACK_UNDER)]
        lanes += [(N.REVIEWER, N.REVIEWER, "Reviewer (gate)"), (N.QA, N.QA, "QA"), (N.JUDGE, N.JUDGE, "Judge")]
        rework, review, judge_edge, merge_edge = E.GATE_REWORK, E.PR_GATE, E.GATE_JUDGE, E.JUDGE_MAIN
    elif ci == Ci.LOCAL:
        first, merged = N.TESTS, N.LAND
        nodes += [(N.TESTS, "Affected tests", c, 1, False, None), (N.LAND, "Land on main", c + 1, 1, False, None),
                  (N.DONE, "Done", c + 2, 1, False, None)]
        finish = [(E.TESTS_LAND, N.TESTS, (N.LAND,), "pass", False, Route.H),
                  (E.TESTS_RED, N.TESTS, (N.BUILDER,), "red", False, Route.BACK_UNDER),
                  (E.LAND_DONE, N.LAND, (N.DONE,), "close", False, Route.H)]
        rework, review, judge_edge, merge_edge = E.TESTS_RED, None, None, E.LAND_DONE
    else:
        first, merged = N.LAND, N.LAND
        nodes += [(N.LAND, "Land on main", c, 1, False, NOTE_NO_TESTS), (N.DONE, "Done", c + 1, 1, False, None)]
        finish = [(E.LAND_DONE, N.LAND, (N.DONE,), "close", False, Route.H)]
        rework, review, judge_edge, merge_edge = None, None, None, E.LAND_DONE
    # the real arrow skips the planned QA and merge queue of `huge`, under them
    edges += [(E.REVIEW_FINISH, N.CHILD_REVIEW, (first,), "all reviewed", False, Route.SKIP_UNDER if huge else Route.H),
              *finish]
    if huge:
        edges.append((E.QUEUE_FINISH, N.MERGE_QUEUE, (first,), "merge", True, Route.H))
    # right after the last box of the top row: it belongs to no role, and the top right corner holds the legend
    wait_col = max(c for _, _, c, r, _, _ in nodes if r == 0) + 1
    nodes.append((N.WAIT, "Waiting", wait_col, 0, False, None))
    lanes.append((N.WAIT, N.WAIT, "Waiting"))
    return Def(kind, ci, tuple(nodes), groups, tuple(edges), tuple(lanes), work=N.BUILDER, spec_from=N.ENGINE,
               spec_edge=E.ENGINE_BUILDER, rework_edge=rework, review_edge=review, gate_nodes=gate, verdict_node=verdict,
               merged=merged, judge_edge=judge_edge, merge_edge=merge_edge, workers=(N.BUILDER, N.CHILD_REVIEW, *gate))


# ── geometry: the same box size and spacing as the old diagram (web/flowapp/src/diagram/layout.ts) ──
NODE_W, NODE_H = 140, 64
X0, COL_W = 10, 208                 # a box every 208 px: 68 px between two boxes for the arrow and its label
ROW_Y = (16, 136, 212)              # command row, work row (build, review, finish), the QA box under the gate's reviewer
FRAME_PAD = 10                      # a group frame sits this far outside its boxes
SIDE = 40                           # the offset of a second arrow on the same side of a box
GAP_TOP_Y = 108                     # the architect's arrow runs in the middle of the 56 px gap above the work row
LOOP_Y, SKIP_Y, BACK_Y = 222, 248, 274   # arrows under the work row (bottom 200), top to bottom
BACK_UNDER_PAD = 20                 # a back arrow from a taller box (the gate frame) runs this far under it
LABEL_UP = 18                       # a label chip sits this far above a horizontal arrow
LABEL_BESIDE = 66                   # … and this far right of an upward arrow
CANVAS_PAD = 30


def geometry(defn):
    """{"canvas": {w, h}, "boxes": {node: {x, y}}, "frames": {group: {x, y, w, h}}, "edges": {edge: {points, label}}}:
    where the flow app draws each box, frame and arrow of an engine diagram."""
    boxes = {nid: {"x": X0 + col * COL_W, "y": ROW_Y[row]} for nid, _, col, row, _, _ in defn.nodes}
    frames = {}
    for gid, _, members in defn.groups:
        xs, ys = [boxes[m]["x"] for m in members], [boxes[m]["y"] for m in members]
        frames[gid] = {"x": min(xs) - FRAME_PAD, "y": min(ys) - FRAME_PAD, "w": max(xs) - min(xs) + NODE_W + 2 * FRAME_PAD,
                       "h": max(ys) - min(ys) + NODE_H + 2 * FRAME_PAD}

    def rect(n):
        if n in frames:
            return frames[n]
        return {"x": boxes[n]["x"], "y": boxes[n]["y"], "w": NODE_W, "h": NODE_H}

    def cx(n):
        r = rect(n)
        return r["x"] + r["w"] / 2

    def top(n):
        return rect(n)["y"]

    def bottom(n):
        r = rect(n)
        return r["y"] + r["h"]

    def left(n):
        return rect(n)["x"]

    def right(n):
        r = rect(n)
        return r["x"] + r["w"]

    def mid(n):   # the arrows of a frame meet it level with the boxes of its top row
        return top(n) + (FRAME_PAD if n in frames else 0) + NODE_H / 2

    edges = {}
    for eid, a, (b, *_), _, _, route in defn.edges:
        if route == Route.H:
            pts = [[right(a), mid(a)], [left(b), mid(b)]]
            lab = [(right(a) + left(b)) / 2, mid(a) - LABEL_UP]
        elif route == Route.V:
            down = top(b) > top(a)
            pts = [[cx(a), bottom(a) if down else top(a)], [cx(b), top(b) if down else bottom(b)]]
            # a downward arrow carries its wait chip on the line; an upward one (non-convergence) has its label beside it,
            # clear of the architect's "frozen design" arrow in the same gap
            lab = [cx(a) + (0 if down else LABEL_BESIDE), (pts[0][1] + pts[1][1]) / 2]
        elif route == Route.GAP_TOP:
            pts = [[cx(a) - SIDE, bottom(a)], [cx(a) - SIDE, GAP_TOP_Y], [cx(b) + SIDE, GAP_TOP_Y], [cx(b) + SIDE, top(b)]]
            lab = [(cx(a) + cx(b)) / 2, GAP_TOP_Y]
        elif route == Route.LOOP_UNDER:
            pts = [[cx(a) - SIDE, bottom(a)], [cx(a) - SIDE, LOOP_Y], [cx(b) + SIDE, LOOP_Y], [cx(b) + SIDE, bottom(b)]]
            lab = [(cx(a) + cx(b)) / 2, LOOP_Y]
        elif route == Route.SKIP_UNDER:
            pts = [[cx(a) + SIDE, bottom(a)], [cx(a) + SIDE, SKIP_Y], [cx(b), SKIP_Y], [cx(b), bottom(b)]]
            lab = [(cx(a) + SIDE + cx(b)) / 2, SKIP_Y]
        else:   # BACK_UNDER: a rework or a red test run, back to the builder under everything between
            low = max(BACK_Y, bottom(a) + BACK_UNDER_PAD)
            pts = [[cx(a), bottom(a)], [cx(a), low], [cx(b) - SIDE, low], [cx(b) - SIDE, bottom(b)]]
            lab = [(cx(a) + cx(b) - SIDE) / 2, low]
        edges[eid] = {"points": pts, "label": lab}
    w = max(right(n) for n in boxes) + FRAME_PAD
    h = max([bottom(n) for n in boxes] + [p[1] for e in edges.values() for p in e["points"]]) + CANVAS_PAD
    return {"canvas": {"w": w, "h": h}, "boxes": boxes, "frames": frames, "edges": edges}


ENGINE_DEFS = {(k, c): _engine(k, c) for k in Kind.ENGINE for c in Ci.ALL}
GEOMETRY = {key: geometry(d) for key, d in ENGINE_DEFS.items()}

# the engine's agents (go/internal/workflow): the builder is role coder; a child's reviewer is role reviewer named
# review-<child>-r<round> or review-<task> (kept); the factory's final gate reviewer is reviewer-<task>
CHILD_REVIEW_MARK = "review-"
SYSTEM_ACTORS = ("factory", "tick", "engine")
ROLE_NODE = {"owner": N.BOSS, "boss": N.BOSS, "coder": N.BUILDER, "qa": N.QA, "judge": N.JUDGE}


def engine_lane(defn, name, role):
    """The lane (= node id) of an agent of an engine run, or None when that role has no place in the diagram."""
    if name in SYSTEM_ACTORS:
        return N.ENGINE
    if role == "reviewer":
        return N.CHILD_REVIEW if CHILD_REVIEW_MARK in (name or "") or N.REVIEWER not in defn.node_lane else N.REVIEWER
    node = ROLE_NODE.get(role)
    return node if node in defn.node_lane else None


# ── workflow.db ──

class Run:
    """What the dashboard knows of one engine run (None fields: not recorded)."""

    def __init__(self, goal_id, story, kind, task_id, state, ci, created, origin, children, incidents):
        self.goal_id, self.story, self.kind, self.task_id = goal_id, story, kind, task_id
        self.state, self.ci, self.created, self.origin = state, ci, created, origin
        self.children, self.incidents = children, incidents


def db_path(con):
    """workflow.db beside the file of the factory DB connection `con`; None for an in-memory DB."""
    main = next((r[2] for r in con.execute("PRAGMA database_list") if r[1] == "main"), "")
    return os.path.join(os.path.dirname(main), WORKFLOW_DB) if main else None


def read_run(con, goal_id, task_id=None):
    """(Run or None, note): the engine run of goal `goal_id` (or whose factory task is `task_id`). No workflow.db or no
    run: (None, None), the old workflow. A file that cannot be read: (None, NOTE_UNREADABLE + reason), shown on the page."""
    path = db_path(con)
    if not path or not os.path.isfile(path):
        return None, None
    try:
        w = sqlite3.connect(f"file:{quote(os.path.abspath(path))}?mode=ro", uri=True, timeout=2)
        try:
            w.row_factory = sqlite3.Row
            w.execute("PRAGMA query_only=ON")
            version = w.execute("PRAGMA user_version").fetchone()[0]
            if version != WORKFLOW_DB_VERSION:
                return None, f"{NOTE_UNREADABLE}: user_version {version}, expected {WORKFLOW_DB_VERSION}"
            r = w.execute("SELECT goal_id, story_key, workflow, task_id, state, ci, created FROM runs "
                          "WHERE goal_id=? OR (? IS NOT NULL AND task_id=?) ORDER BY goal_id=? DESC LIMIT 1",
                          (goal_id, task_id, task_id, goal_id)).fetchone()
            if r is None:
                return None, None
            kids = [dict(k) for k in w.execute(
                "SELECT c.child_key AS key, c.story_key AS story, c.state, c.rounds, c.position FROM children c "
                "LEFT JOIN run_stories s ON s.goal_id=c.goal_id AND s.story_key=c.story_key WHERE c.goal_id=? "
                "ORDER BY COALESCE(s.position, 0), c.position, c.child_key", (r["goal_id"],))]
            incs = [dict(i) for i in w.execute(
                "SELECT id, child_key, kind, cause, actor, round, summary, created FROM incidents WHERE goal_id=? ORDER BY id",
                (r["goal_id"],))]
        finally:
            w.close()
    except sqlite3.Error as e:
        return None, f"{NOTE_UNREADABLE}: {e}"
    ev = con.execute("SELECT action FROM events WHERE entity='workflow' AND entity_id=? AND action IN (?, ?) "
                     "ORDER BY id DESC LIMIT 1", (r["goal_id"], *Origin.EVENTS)).fetchone()
    kind = r["workflow"] if r["workflow"] in Kind.ENGINE else Kind.HUGE   # an unknown name: the fullest diagram
    ci = r["ci"] if r["ci"] in Ci.ALL else Ci.GITHUB
    return Run(r["goal_id"], r["story_key"], kind, r["task_id"], r["state"], ci, r["created"],
               Origin.EVENTS.get(ev["action"]) if ev else None, kids, incs), None
