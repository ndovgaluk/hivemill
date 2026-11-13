// Sequence tab, as in the design: one card per phase (from the API), opened to a vertical list of its actions.
import { useEffect, useState } from "react";

import { EventKind, SelectionKind, Severity, SpanKind } from "../constants";
import { fmtCost, fmtDuration, fmtTokens } from "../format";
import { Body } from "../instructions/Body";
import { CopyReference } from "../reference/CopyReference";
import { useSelection } from "../selection";
import type { FlowData, FlowEvent, Phase } from "../types";
import { clock, QUIET_GAP_S, tickLabel } from "./time";
import styles from "./timeline.module.css";

export const SEQUENCE_HELP = "Every action in the order it started, grouped by phase. Click a group to open it. "
  + "On a message, click “Instructions” to read what was passed on.";
const GAP_SUFFIX = "with no new action starting";
export const EXPAND = "Expand";       // the small hover button after a title: same as the Details/Instructions chip
export const COLLAPSE = "Collapse";
const ARROW = " → ";
const FAIL_SUFFIX = ", ended in FAIL";
const NOW = "now";

interface Item {
  t: number;
  key: string;
  event?: FlowEvent;
  session?: { name: string; lane: string; start: number; end: number | null; kind: SpanKind };
}

const CHIP: Record<EventKind, string> = { [EventKind.Msg]: "Instructions", [EventKind.Verdict]: "Verdict", [EventKind.Status]: "Details" };
const BODY_LABEL: Record<EventKind, string> = { [EventKind.Msg]: "Message", [EventKind.Verdict]: "Verdict", [EventKind.Status]: "Status update" };

function flags(evs: FlowEvent[]) {
  const verdicts = evs.filter((e) => e.kind === EventKind.Verdict);
  return [
    { n: verdicts.filter((e) => e.severity === Severity.Bad).length, text: "failed", cls: styles.pillBad },
    { n: verdicts.filter((e) => e.severity === Severity.Ok).length, text: "passed", cls: styles.pillOk },
    { n: evs.filter((e) => e.severity === Severity.Warn).length, text: "to check", cls: styles.pillWarn },
  ].filter((f) => f.n > 0);
}

const tokenSum = (e: FlowEvent) => (e.tokens ? e.tokens.input + e.tokens.output + e.tokens.cache_read + e.tokens.cache_write : null);
const offset = (s: number | null) => (s === null ? "" : `+${fmtDuration(s)}`);

function Marker({ e, kind }: { e?: FlowEvent; kind?: SpanKind }) {
  if (!e) return <span className={`${styles.mk} ${styles.mkSpan} ${kind === SpanKind.Fail ? styles.mkSpanFail : ""}`} />;
  const glyph = e.kind === EventKind.Verdict ? (e.severity === Severity.Bad ? "✗" : "✓") : "";
  return <span className={`${styles.mk} ${styles[`mk_${e.kind}`] ?? ""} ${styles[`mk_${e.severity}`] ?? ""}`}>{glyph}</span>;
}

export function Sequence({ data, open, toggle, onOpenInstructions }: {
  data: FlowData;
  open: Set<string>;
  toggle: (phaseId: string, open?: boolean) => void;
  onOpenInstructions: (edgeId: string, eventId: string) => void;
}) {
  const sel = useSelection();
  const [bodies, setBodies] = useState<Set<string>>(() => new Set());
  const byId = new Map(data.events.map((e) => [e.id, e]));
  const selectedId = sel.selection?.kind === SelectionKind.Event ? sel.selection.id : null;

  useEffect(() => {
    // an event selected anywhere opens the phase that holds it
    if (!selectedId) return;
    const p = data.phases.find((ph) => ph.event_ids.includes(selectedId));
    if (p) toggle(p.id, true);
  }, [selectedId, data.phases, toggle]);

  const flip = (id: string) => setBodies((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  let prevEnd: number | null = null;
  return (
    <div className={styles.seq}>
      <p className={styles.help}>{SEQUENCE_HELP}</p>
      <ol className={styles.phases}>
        {data.phases.map((p: Phase) => {
          const evs = p.event_ids.map((id) => byId.get(id)).filter((e): e is FlowEvent => !!e);
          const timed = evs.filter((e) => e.t_s !== null);
          const first = timed[0];
          const last = timed[timed.length - 1];
          const gap = prevEnd !== null && first && first.t_s! - prevEnd >= QUIET_GAP_S ? first.t_s! - prevEnd : null;
          if (last) prevEnd = Math.max(prevEnd ?? 0, last.t_s!);
          const isOpen = open.has(p.id);
          const hot = sel.selection === null || evs.some((e) => sel.hot.events.has(e.id));
          const range = first && last ? (clock(first.ts) === clock(last.ts) ? clock(first.ts) : `${clock(first.ts)} – ${clock(last.ts)}`) : "";
          const items: Item[] = evs.map((e) => ({ t: e.t_s ?? Infinity, key: e.id, event: e }));
          for (const r of p.span_refs as { lane: string; row: string; index: number }[]) {
            const s = data.lanes.find((l) => l.id === r.lane)?.rows.find((x) => x.name === r.row)?.spans[r.index];
            if (s && s.start_s !== null)
              items.push({ t: s.start_s, key: `${r.lane}/${r.row}/${r.index}`, session: {
                name: r.row, lane: data.lanes.find((l) => l.id === r.lane)?.label ?? r.lane, start: s.start_s, end: s.end_s, kind: s.kind,
              } });
          }
          items.sort((a, b) => a.t - b.t);
          return (
            <li key={p.id} className={styles.phase} data-testid={`flow-phase-${p.id}`} data-dim={!hot}>
              {gap !== null ? (
                <p className={styles.gap}><span aria-hidden="true">⋯</span> {fmtDuration(gap).replace(/ \d+s$/, "")} {GAP_SUFFIX}</p>
              ) : null}
              <div className={styles.card}>
                <button type="button" className={styles.phaseHead} aria-expanded={isOpen} onClick={() => toggle(p.id)}>
                  <span className={styles.caret} aria-hidden="true">{isOpen ? "▾" : "▸"}</span>
                  <span className={styles.phaseText}>
                    <span className={styles.phaseTitle}>{p.title}</span>
                    <span className={styles.summary}>{p.summary}</span>
                  </span>
                  <span className={styles.phaseMeta}>
                    {flags(evs).map((f) => <span key={f.text} className={`${styles.pill} ${f.cls}`}>{f.n} {f.text}</span>)}
                    <span className={styles.mono}>{range}{range ? " · " : ""}{items.length} {items.length === 1 ? "action" : "actions"}</span>
                  </span>
                </button>
                {isOpen ? (
                  <ol className={styles.items}>
                    {items.map((it, i) => {
                      const e = it.event;
                      const on = !!e && selectedId === e.id;
                      const bodyOpen = !!e && bodies.has(e.id);
                      const toggleBody = () => {
                        if (!e) return;
                        flip(e.id);
                        if (!bodyOpen) sel.select({ kind: SelectionKind.Event, id: e.id });
                      };
                      const pick = () => e && sel.select({ kind: SelectionKind.Event, id: e.id });
                      return (
                        <li key={it.key} className={styles.itemWrap}
                            data-hot={e && sel.selection !== null ? sel.hot.events.has(e.id) : undefined}>
                          {/* the whole row selects: a click on its empty part lands on the row itself */}
                          <div className={styles.itemRow} onClick={(ev) => ev.target === ev.currentTarget && pick()}>
                            <button type="button" className={styles.item} aria-pressed={on} onClick={pick}>
                              <span className={styles.when}>
                                <span>{e ? clock(e.ts) : ""}</span>
                                <span className={styles.offset}>{offset(e ? e.t_s : it.session!.start)}</span>
                              </span>
                              <span className={styles.rail} data-first={i === 0} data-last={i === items.length - 1}>
                                <Marker e={e} kind={it.session?.kind} />
                              </span>
                              <span className={styles.what}>
                                <span className={styles.titleLine}>
                                  <span className={`${styles.title} ${e ? styles[`t_${e.severity}`] ?? "" : it.session!.kind === SpanKind.Fail ? styles.t_bad : ""} ${e?.kind === EventKind.Verdict ? styles.strong : ""}`}>
                                    {e ? e.title : `${it.session!.name} session${it.session!.kind === SpanKind.Fail ? FAIL_SUFFIX : ""}`}
                                  </span>
                                  <span className={styles.mono} title={e?.cost_note ?? undefined}>
                                    {e ? `${fmtTokens(tokenSum(e))} tok · ${fmtCost(e.cost)}`
                                      : fmtDuration(it.session!.end !== null ? it.session!.end - it.session!.start : null)}
                                  </span>
                                </span>
                                <span className={styles.sub}>
                                  {e ? <>{e.from ?? e.from_node ?? "?"}{ARROW}{e.to ?? e.to_node ?? "?"}</>
                                    : `${it.session!.lane} · ${tickLabel(data.start, it.session!.start, false)} to ${
                                      it.session!.end === null ? NOW : tickLabel(data.start, it.session!.end, false)}`}
                                </span>
                              </span>
                            </button>
                            {e ? (
                              <button type="button" className={styles.peek} aria-expanded={bodyOpen}
                                      aria-label={bodyOpen ? COLLAPSE : EXPAND} title={bodyOpen ? COLLAPSE : EXPAND}
                                      onClick={toggleBody}>
                                <span aria-hidden="true">{bodyOpen ? "▴" : "▾"}</span>
                              </button>
                            ) : null}
                            {e ? (
                              <button type="button" className={styles.chipBtn} aria-expanded={bodyOpen} onClick={toggleBody}>
                                {bodyOpen ? "Hide ▴" : `${CHIP[e.kind]} ▾`}
                              </button>
                            ) : null}
                            {e ? <CopyReference data={data} selection={{ kind: SelectionKind.Event, id: e.id }} icon /> : null}
                          </div>
                          {e && bodyOpen ? (
                            <div className={styles.inline}>
                              <p className={styles.inlineHead}>
                                <span className={styles.inlineLabel}>{BODY_LABEL[e.kind]}</span>
                                <span className={styles.mono}>{e.from ?? "?"}{ARROW}{e.to ?? "?"}</span>
                              </p>
                              <Body showText={data.show_text} html={e.body_html} />
                              {e.is_instruction && e.edge ? (
                                <button type="button" className={styles.viewer} onClick={() => onOpenInstructions(e.edge!, e.id)}>
                                  Open in instruction viewer
                                </button>
                              ) : null}
                            </div>
                          ) : null}
                        </li>
                      );
                    })}
                  </ol>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
