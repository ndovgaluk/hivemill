// Lanes tab: one lane per role with work/wait/fail spans and event marks; expands to one row per agent.
import { useEffect, useRef } from "react";

import { SelectionKind, SpanKind } from "../constants";
import { MESSAGE_ONLY, MSGS_ONLY, NO_SESSIONS } from "../diagram/BoxNode";
import { fmtCost, fmtDuration } from "../format";
import { useSelection } from "../selection";
import type { FlowData, FlowEvent, Lane, Span } from "../types";
import { axisLength, clock, markName, pct, tickLabel, ticks } from "./time";
import styles from "./timeline.module.css";


function spanWork(spans: Span[]): number | null {
  let sum = 0;
  let any = false;
  for (const s of spans)
    if (s.kind !== SpanKind.Wait && s.start_s !== null && s.end_s !== null) {
      sum += s.end_s - s.start_s;
      any = true;
    }
  return any ? sum : null;
}

function laneTotal(data: FlowData, l: Lane): string {
  if (!l.rows.length) return MESSAGE_ONLY.has(l.node) ? MSGS_ONLY : NO_SESSIONS;
  const work = fmtDuration(spanWork(l.rows.flatMap((r) => r.spans)));
  const cost = data.nodes.find((n) => n.id === l.node)?.cost ?? null;
  return cost === null ? work : `${work} · ${fmtCost(cost)}`;
}

function Axis({ data, total, zoom }: { data: FlowData; total: number; zoom: number }) {
  return (
    <div className={`${styles.row} ${styles.axis}`} aria-hidden="true">
      <span className={`${styles.label} ${styles.sticky} ${styles.axisLabel}`}>from {clock(data.start)} · {fmtDuration(total)}</span>
      <div className={styles.track}>
        {ticks(total, zoom).map(({ t, withDate }) => (
          <span key={t} className={styles.tick} style={{ left: `${pct(t, total)}%` }}>{tickLabel(data.start, t, withDate)}</span>
        ))}
      </div>
    </div>
  );
}

function Spans({ spans, total }: { spans: Span[]; total: number }) {
  return (
    <>
      {spans.filter((s) => s.start_s !== null).map((s, i) => {
        const left = pct(s.start_s!, total);
        const width = Math.max(0.3, pct((s.end_s ?? total) - s.start_s!, total));
        return (
          <span key={i} className={`${styles.span} ${styles[s.kind] ?? ""}`} data-kind={s.kind} data-left={left} data-width={width}
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`${s.kind}: ${fmtDuration(s.end_s !== null ? s.end_s - s.start_s! : null)}${s.note ? ` (${s.note})` : ""}`} />
        );
      })}
    </>
  );
}

function Marks({ events, total }: { events: FlowEvent[]; total: number }) {
  const sel = useSelection();
  return (
    <>
      {events.filter((e) => e.t_s !== null).map((e) => {
        const on = sel.selection?.kind === SelectionKind.Event && sel.selection.id === e.id;
        return (
          <button key={e.id} type="button" className={`${styles.mark} ${styles[e.kind] ?? ""} ${styles[e.severity] ?? ""}`}
                  style={{ left: `${pct(e.t_s!, total)}%` }} data-kind={e.kind} data-mark={e.id}
                  data-hot={sel.hot.events.has(e.id)} aria-pressed={on} aria-label={markName(e)} title={markName(e)}
                  onClick={() => sel.select({ kind: SelectionKind.Event, id: e.id })} />
        );
      })}
    </>
  );
}

export function Lanes({ data, zoom, expanded, toggle }: {
  data: FlowData;
  zoom: number;
  expanded: Set<string>;
  toggle: (laneId: string, open?: boolean) => void;
}) {
  const sel = useSelection();
  const total = axisLength(data);
  const ref = useRef<HTMLDivElement>(null);
  const selectedId = sel.selection?.kind === SelectionKind.Event ? sel.selection.id : null;

  useEffect(() => {
    // an event selected anywhere: open its lane and bring its mark into view
    if (!selectedId) return;
    const ev = data.events.find((e) => e.id === selectedId);
    if (ev?.lane) toggle(ev.lane, true);
    ref.current?.querySelector(`[data-mark="${selectedId}"]`)?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [selectedId, data.events, toggle]);

  return (
    <div className={styles.scroller} ref={ref}>
      <div className={styles.grid} data-zoom={zoom} style={{ width: `${zoom * 100}%` }}>
        {sel.hot.cursor !== null ? (
          <span className={styles.cursor} data-testid="flow-cursor" style={{ left: `calc(var(--label-w) + (100% - var(--label-w)) * ${pct(sel.hot.cursor, total) / 100})` }} />
        ) : null}
        <Axis data={data} total={total} zoom={zoom} />
        {data.lanes.map((l) => {
          const open = expanded.has(l.id);
          const hot = sel.hot.lanes.has(l.id);
          const evs = data.events.filter((e) => e.lane === l.id);
          return (
            <div key={l.id} className={styles.lane} data-testid={`flow-lane-${l.id}`} data-hot={hot}
                 data-dim={sel.selection !== null && !hot}>
              <div className={styles.row}>
                <button type="button" className={`${styles.label} ${styles.sticky}`} data-sticky="true" aria-expanded={open}
                        aria-label={l.label}
                        onClick={() => {
                          sel.select({ kind: SelectionKind.Node, id: l.node });
                          if (l.rows.length) toggle(l.id);
                        }}>
                  <span className={styles.laneName}>
                    <span className={styles.caret} aria-hidden="true">{l.rows.length ? (open ? "▾" : "▸") : ""}</span>
                    {l.label}
                  </span>
                  <span className={styles.total}>{laneTotal(data, l)}</span>
                </button>
                <div className={styles.track}>
                  <Spans spans={l.rows.flatMap((r) => r.spans)} total={total} />
                  <Marks events={evs} total={total} />
                </div>
              </div>
              {open
                ? l.rows.map((r) => (
                    <div key={r.name} className={`${styles.row} ${styles.sub}`} role="group" aria-label={r.name}>
                      <span className={`${styles.label} ${styles.sticky} ${styles.rowLabel}`} data-sticky="true">
                        <span>{r.name}</span>
                        <span className={styles.total}>{fmtDuration(spanWork(r.spans))}</span>
                      </span>
                      <div className={styles.track}>
                        <Spans spans={r.spans} total={total} />
                        <Marks events={evs.filter((e) => e.row === r.name)} total={total} />
                      </div>
                    </div>
                  ))
                : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
