"""SVG chart primitives for the web UI (G-019 B4, design components C8-C10). Stdlib only.

Every function returns html.Safe built with html.el(), so labels are escaped. Geometry lives in SVG attributes
(no inline style attributes, the CSP is style-src 'self'); colours come from the app.css classes (fill-*, track, tick, spark, col),
so dark mode and the tokens apply. Every chart has a role="img" aria-label summary; sparkline and columns are
followed by a visually hidden <table class="sr-only"> with the same data.

B5 and B6 import from here; keep the signatures stable:
  meter(value, total, label, noun="tasks")           C8 progress bar with the label beside it
  gauge(label, value_text, pct, thresholds, zone, caption)   C9 labelled threshold gauge row
  gauge_bar(pct, thresholds, tone, aria)             the bare C9 bar (stack two for 5-hour and weekly)
  sparkline(points, label, caption="per day")        C10 120 x 24 trend line
  columns(points, label, height=96)                  C10 column chart, one bar per day
`points` are (day "YYYY-MM-DD", number) pairs, oldest first.
"""
from web.components import empty_state
from web.html import Safe, dur, el, h
from web.queries import FlowState

TONES = ("success", "warning", "danger", "neutral")
SPARK_W, SPARK_H, SPARK_PAD = 120, 24, 3
COL_W = 24
MAX_W = 336   # widest chart that still fits a phone card at 1:1, so its labels keep their size
COL_TOP, COL_BOTTOM = 14, 16
# Horizontal padding inside the SVG so 5-character date labels (middle-anchored ~±15 user units) stay inside the viewBox
# when the chart scales to the card (see web-redesign-review finding: first col-x clipped left of viewBox 0).
LABEL_PAD = 18.0


def _svg(inner, view_box, **attrs):
    """<svg> root. html.el() only takes lower-case attribute names, and SVG needs viewBox and preserveAspectRatio, so the
    root is assembled here; every value goes through html.h()."""
    a = {"viewBox": view_box, **attrs}
    return Safe("<svg" + "".join(f' {k}="{h(v)}"' for k, v in a.items() if v is not None) + ">" + "".join(str(i) for i in inner) + "</svg>")


def _line(x, y1, y2, **attrs):
    """Vertical <line>; html.el() rejects attribute names with digits (x1), so it is assembled here."""
    a = {"x1": x, "x2": x, "y1": y1, "y2": y2, **attrs}
    return Safe("<line" + "".join(f' {k}="{h(v)}"' for k, v in a.items()) + "/>")


def _pct(v):
    try:
        return max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _num(v):
    return f"{v:.1f}"


def compact(n):
    """Short figure for a count: 1500 -> "1.5k", 48567200 -> "48.6M"; below 1000 the number as it is. Bar labels, the
    aria-label and web.views.tokens use it, so no figure ever prints as 4.85672e+07."""
    n = n or 0
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        k = f"{n / 1_000:.1f}"
        return f"{k}k" if abs(float(k)) < 1000 else f"{n / 1_000_000:.1f}M"   # 999,999 is 1.0M, not 1000.0k
    return f"{n:g}"


def _exact(v):
    """Exact value for a tooltip or table cell: whole numbers with thousands separators (48,567,200), never an exponent."""
    return f"{int(v):,}" if float(v).is_integer() else compact(v)


def _day(iso):
    return iso[5:10] if len(iso) >= 10 else iso


def _data_table(points, label, caption, unit="day"):
    rows = [el("tr", el("td", d), el("td", _exact(n))) for d, n in points]
    return el("table", el("caption", caption), el("thead", el("tr", el("th", unit.capitalize(), scope="col"), el("th", label.capitalize(), scope="col"))),
              el("tbody", rows), class_="sr-only")


def meter(value, total, label, noun="tasks"):
    """C8: a 100 x 6 track with a fill whose width is exact (value / total, one decimal; 3 of 9 -> 33.3), not a 5 % step.
    `label` ("3/9 tasks") sits beside the bar, not inside it. aria-label "3 of 9 tasks done" (`noun` is the unit)."""
    w = _pct(100 * value / total) if total else 0.0
    bar = _svg([el("rect", class_="track", x=0, y=0, width=100, height=6),
                el("rect", class_="fill-data1", x=0, y=0, width=_num(w), height=6)], "0 0 100 6",
               preserveAspectRatio="none", role="img", focusable="false", **{"aria-label": f"{value} of {total} {noun} done"},
               **{"class": "meter-svg"})
    return el("div", bar, el("span", label, class_="lbl"), class_="meter")


def gauge_bar(pct, thresholds, tone, aria):
    """The bare C9 bar: 100 x 8 track, a fill classed by `tone` (success|warning|danger) and a 2 px tick at each
    threshold percentage. Colour is never the only signal: callers put the zone word in text next to it."""
    tone = tone if tone in TONES else "success"
    ticks = [_line(_num(_pct(t)), 0, 8, **{"class": "tick"}) for t in thresholds or ()]
    return _svg([el("rect", class_="track", x=0, y=0, width=100, height=8),
                 el("rect", class_=f"fill-{tone}", x=0, y=0, width=_num(_pct(pct)), height=8), *ticks], "0 0 100 8",
                preserveAspectRatio="none", role="img", focusable="false", **{"aria-label": aria}, **{"class": "gauge"})


def gauge(label, value_text, pct, thresholds, zone, caption=None):
    """C9: row of label, bar, value. `pct` is the fill (0-100), `thresholds` the tick positions (percentages), `zone`
    a (tone, word) pair such as ("danger", "Over cap"); the word is always shown, so colour is not the only signal."""
    tone, word = zone
    aria = f"{label} {value_text}, {word}" + (f", {caption}" if caption else "")
    sub = el("span", el("b", word, class_=f"gz fg-{tone}"), f" · {caption}" if caption else None)
    return el("div", el("span", label, class_="gl"), gauge_bar(pct, thresholds, tone, aria),
              el("span", value_text, sub, class_="gv"), class_="gauge-row")


def _summary(points, label, unit="day"):
    total = sum(n for _, n in points)
    peak = max((n for _, n in points), default=0)
    text = f"{compact(total)} {label} in {len(points)} {unit}s"
    if peak > 0:
        day = [d for d, n in points if n == peak][-1]
        text += f", peak {compact(peak)} on {_day(day)}"
    return text


def sparkline(points, label, caption="per day"):
    """C10: 120 x 24 polyline of `points` with the last point emphasised, aria-label "8 merges in 14 days, peak 3 on
    10-21" (`label` is the plural noun), the sr-only data table and the visible `caption` ("per day")."""
    points = list(points)
    n = len(points)
    top = max((v for _, v in points), default=0) or 1
    step = (SPARK_W - 2 * SPARK_PAD) / (n - 1) if n > 1 else 0
    xy = [(SPARK_PAD + i * step, SPARK_H - SPARK_PAD - (v / top) * (SPARK_H - 2 * SPARK_PAD)) for i, (_, v) in enumerate(points)]
    shapes = []
    if xy:
        shapes = [el("polyline", points=" ".join(f"{_num(x)},{_num(y)}" for x, y in xy)),
                  el("circle", class_="spark-last", cx=_num(xy[-1][0]), cy=_num(xy[-1][1]), r=2.5)]
    svg = _svg(shapes, f"0 0 {SPARK_W} {SPARK_H}", width=SPARK_W, height=SPARK_H, role="img", focusable="false",
               **{"aria-label": _summary(points, label)}, **{"class": "spark"})
    return el("span", svg, _data_table(points, label, f"{label.capitalize()} per day, last {n} days"),
              el("span", caption, class_="spark-cap"), class_="spark-wrap")


def columns(points, label, height=96, unit="day"):
    """C10: one <rect> per day, each with a <title> holding its exact value; value labels on non-zero bars when there
    are 14 days or fewer; an x label every 7th day. Empty data (no points, or all zero) gives the calm C14 line
    "No <label> in this range" instead of an empty axis. `unit` names what one bar is ("day" or "week") in the aria-label
    and the data table."""
    points = list(points)
    if not points or not any(v for _, v in points):
        return empty_state(f"No {label} in this range")
    n = len(points)
    top = max(v for _, v in points)
    plot = height - COL_TOP - COL_BOTTOM
    # A value label is about 6 px per character at 10 px. Longer labels (48.6M) widen the column while the chart still fits
    # a phone (MAX_W); beyond that every k-th bar is labelled, so labels never overlap. Short labels keep COL_W.
    label_w = 6 * max((len(compact(v)) for _, v in points if v), default=0) + 6
    col_w = COL_W if label_w <= COL_W else min(label_w, max(COL_W, MAX_W // n))
    stride = 1 if label_w <= col_w else -(-label_w // col_w)
    plot_left = LABEL_PAD
    inner_w = n * col_w
    last_i = n - 1
    bars, texts = [], []
    for i, (day, v) in enumerate(points):
        bh = max(1.0, v / top * plot) if v else 1.0
        x = plot_left + i * col_w + 4
        bars.append(el("rect", el("title", f"{_day(day)}: {_exact(v)} {label}"), class_="col col--zero" if not v else "col",
                       x=x, y=_num(height - COL_BOTTOM - bh), width=col_w - 8, height=_num(bh)))
        if v and n <= 14 and i % stride == 0:
            texts.append(el("text", compact(v), class_="col-val", x=_num(x + (col_w - 8) / 2), y=_num(height - COL_BOTTOM - bh - 3),
                            text_anchor="middle"))
        if i % 7 == 0:
            cx = x + (col_w - 8) / 2
            ta = "start" if i == 0 else "end" if i == last_i else "middle"
            texts.append(el("text", _day(day), class_="col-x", x=_num(cx), y=height - 3, text_anchor=ta))
    vb_w = inner_w + 2 * LABEL_PAD
    svg = _svg([*bars, *texts], f"0 0 {int(vb_w)} {height}", height=height, role="img", focusable="false",
               preserveAspectRatio="xMidYMin meet", **{"aria-label": _summary(points, label, unit)}, **{"class": "cols"})
    return el("div", svg, _data_table(points, label, f"{label.capitalize()} per {unit}, last {n} {unit}s", unit), class_="cols-wrap")


# ───────────── task flow diagram (DVDG-544) ─────────────
FLOW_W, FLOW_H, FLOW_GAP, FLOW_TOP, FLOW_PAD = 132, 62, 34, 12, 8
FLOW_LOOP_DROP = 34   # how far the rejection loop dips below the boxes
FLOW_LOOP_FROM, FLOW_LOOP_TO = "review", "coding"   # stage keys of queries.FLOW_STAGES: a rejection sends work back to coding


def flow_stage_id(key):
    """Anchor of a task stage's block under the diagram (a node links here)."""
    return f"flow-s-{key}"


def flow_in_id(key):
    """Anchor of the instructions a stage received (the arrow into the stage links here)."""
    return f"flow-in-{key}"


def goal_node_id(role):
    return f"gf-n-{role}"


def goal_link_id(a, b):
    return f"gf-e-{a}-{b}"


def _flow_node(i, st, live):
    x = FLOW_PAD + i * (FLOW_W + FLOW_GAP)
    cls = f"flow-node flow-node--{st['state']}" + (" flow-node--live" if live else "")
    tip = [f"{st['label']}: {st['state']}, {dur(st['seconds'])}"] + [f"{n['ts'] or '?'}  {n['text']}" for n in st["notes"]]
    if st["more"]:
        tip.insert(1, f"(+{st['more']} earlier)")
    tip.append("Click to highlight this stage below.")
    kids = [el("title", "\n".join(tip)),
            el("rect", class_="flow-box", x=x, y=FLOW_TOP, width=FLOW_W, height=FLOW_H, rx=8),
            el("text", st["label"], class_="flow-label", x=x + 10, y=FLOW_TOP + 22),
            el("text", dur(st["seconds"]) if st["seconds"] is not None else "", class_="flow-time", x=x + 10, y=FLOW_TOP + 40)]
    if live:
        kids.append(el("text", f"● {live['role']} working", class_="flow-badge", x=x + 10, y=FLOW_TOP + 55))
    return el("a", el("g", *kids, class_=cls), href=f"#{flow_stage_id(st['key'])}", class_="flow-link")


def flow_diagram(flow):
    """DVDG-544: the task's stages left to right; the current one pulses (stronger, with a moving arrow, while an agent
    works on it); time spent under each label; the rejection loop back to Coding; notes in each node's <title> tooltip.
    Every node, arrow and the loop is a link to its block under the diagram, which CSS :target highlights. No JS, no
    inline style (CSP)."""
    stages = flow["stages"]
    live = flow.get("live")
    nodes, edges = [], []
    for i, st in enumerate(stages):
        nodes.append(_flow_node(i, st, live if st["state"] == FlowState.CURRENT else None))
        if i:
            x1, x2, y = FLOW_PAD + i * (FLOW_W + FLOW_GAP) - FLOW_GAP, FLOW_PAD + i * (FLOW_W + FLOW_GAP) - 4, FLOW_TOP + FLOW_H / 2
            cls = "flow-edge" + (" flow-edge--active" if live and st["state"] == FlowState.CURRENT
                                 else " flow-edge--done" if st["state"] in (FlowState.DONE, FlowState.CURRENT) else "")
            n_in = sum(1 for n in st["notes"] if n.get("incoming"))
            edges.append(el("a", el("title", f"{stages[i - 1]['label']} → {st['label']}: {n_in} instruction(s). Click to highlight."),
                            Safe(f'<line class="flow-hit" x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>'),
                            Safe(f'<line class="{cls}" x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>'),
                            el("polygon", class_="flow-arrow", points=f"{x2},{y} {x2 - 7},{y - 4} {x2 - 7},{y + 4}"),
                            href=f"#{flow_in_id(st['key'])}", class_="flow-link"))
    keys = [s["key"] for s in stages]
    if flow["rejections"] and FLOW_LOOP_FROM in keys and FLOW_LOOP_TO in keys:
        cx = FLOW_PAD + keys.index(FLOW_LOOP_TO) * (FLOW_W + FLOW_GAP) + FLOW_W / 2
        rx = FLOW_PAD + keys.index(FLOW_LOOP_FROM) * (FLOW_W + FLOW_GAP) + FLOW_W / 2
        y0, y1 = FLOW_TOP + FLOW_H, FLOW_TOP + FLOW_H + FLOW_LOOP_DROP
        n = flow["rejections"]
        loop = f"M{rx},{y0} C{rx},{y1} {cx},{y1} {cx},{y0}"
        edges.append(el("a", el("title", "Rejections: click to highlight the review stage"),
                        el("path", class_="flow-hit", d=loop), el("path", class_="flow-loop", d=loop),
                        el("text", f"rejected {n}× · {flow['attempts']} attempts", class_="flow-loop-label",
                           x=(cx + rx) / 2, y=y1 + 4, text_anchor="middle"),
                        href=f"#{flow_stage_id(FLOW_LOOP_FROM)}", class_="flow-link"))
    width = FLOW_PAD * 2 + len(stages) * FLOW_W + (len(stages) - 1) * FLOW_GAP
    height = FLOW_TOP + FLOW_H + FLOW_LOOP_DROP + 12
    where = next((s["label"] for s in stages if s["state"] == FlowState.CURRENT), "finished")
    svg = _svg([*edges, *nodes], f"0 0 {width} {height}", role="img", focusable="false",
               **{"aria-label": f"Task flow, now at: {where}", "class": "flow-svg"})
    return el("div", svg, class_="flow")


# ───────────── goal flow diagram (DVDG-544): roles and who instructed whom ─────────────
GF_W, GF_H, GF_GAP, GF_PAD, GF_ARC = 108, 54, 22, 8, 26   # GF_ARC: arc height per role between the two ends


def goal_diagram(gf):
    """The goal's roles left to right (Owner → Boss → Director → System → Lead → PM → Coders → Reviewer → QA → Judge),
    each with its agent count and time alive (pulsing while one of its agents is live), and one arc per pair of roles
    that messaged each other, labelled with the counts both ways. A node links to that role's block under the diagram
    (its agents and their own summaries), an arc to the block with the messages between the two roles (:target
    highlight). No JS, no inline style (CSP)."""
    nodes, links = gf["nodes"], gf["links"]
    if not nodes:
        return empty_state("No agents or messages on this goal yet.")
    pos = {n["key"]: i for i, n in enumerate(nodes)}
    span = max((abs(pos[l["b"]] - pos[l["a"]]) for l in links), default=1)
    top = GF_PAD + 14 + GF_ARC * span
    cx = lambda k: GF_PAD + pos[k] * (GF_W + GF_GAP) + GF_W / 2  # noqa: E731
    arcs = []
    for l in links:
        x1, x2, d = cx(l["a"]), cx(l["b"]), abs(pos[l["b"]] - pos[l["a"]])
        apex = top - GF_ARC * d
        path = f"M{x1},{top} C{x1},{apex} {x2},{apex} {x2},{top}"
        label = f"{l['ab']}→ {l['ba']}←" if l["ba"] else f"{l['ab']}→"
        names = {n["key"]: n["label"] for n in nodes}
        arcs.append(el("a", el("title", f"{names[l['a']]} ⇄ {names[l['b']]}: {l['ab'] + l['ba']} message(s). Click to highlight."),
                       el("path", class_="flow-hit", d=path), el("path", class_="gflow-arc", d=path),
                       el("text", label, class_="gflow-count", x=(x1 + x2) / 2, y=top - GF_ARC * d * 0.75 - 3,
                          text_anchor="middle"),
                       href=f"#{goal_link_id(l['a'], l['b'])}", class_="flow-link"))
    boxes = []
    for n in nodes:
        x = GF_PAD + pos[n["key"]] * (GF_W + GF_GAP)
        cls = "flow-node " + ("flow-node--current flow-node--live" if n["live"] else "flow-node--done" if n["agents"] else "flow-node--pending")
        sub = f"{len(n['agents'])} agent{'s' if len(n['agents']) != 1 else ''}" if n["agents"] else ""
        boxes.append(el("a", el("g", el("title", f"{n['label']}: {sub or 'no agent'}{', ' + dur(n['seconds']) if n['agents'] else ''}"
                                                 f"{' · working now' if n['live'] else ''}. Click to highlight."),
                                el("rect", class_="flow-box", x=x, y=top, width=GF_W, height=GF_H, rx=8),
                                el("text", n["label"], class_="flow-label", x=x + 9, y=top + 21),
                                el("text", sub, class_="flow-time", x=x + 9, y=top + 37),
                                el("text", dur(n["seconds"]) if n["agents"] else "", class_="flow-time", x=x + 9, y=top + 50),
                                class_=cls),
                          href=f"#{goal_node_id(n['key'])}", class_="flow-link"))
    width = GF_PAD * 2 + len(nodes) * GF_W + (len(nodes) - 1) * GF_GAP
    svg = _svg([*arcs, *boxes], f"0 0 {width} {top + GF_H + GF_PAD}", role="img", focusable="false",
               **{"aria-label": f"Goal flow: {len(nodes)} roles, {len(links)} links", "class": "flow-svg"})
    return el("div", svg, class_="flow")
