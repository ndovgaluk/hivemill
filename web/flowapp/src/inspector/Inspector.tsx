// The side panel: overview rankings with nothing selected, else the detail of the selected box, arrow or step.
import { Lens, Scope, SelectionKind, Severity } from "../constants";
import { fmtCost, fmtCount, fmtDuration, fmtTokens } from "../format";
import { timeOrder, useSelection } from "../selection";
import { Body } from "../instructions/Body";
import { CopyReference, RefChip } from "../reference/CopyReference";
import { clock, route } from "../timeline/time";
import type { FlowData, FlowEdge, FlowEvent, FlowNode, Tokens } from "../types";
import styles from "./inspector.module.css";
import { tokenSum } from "./SummaryBar";

export { HIDDEN_TEXT } from "../instructions/Body";
const AROUND = 2;
const UNATTRIBUTED_LABEL = "Unattributed sessions";
const noop = () => {};
const OVERVIEW = "Overview";
const TIME_TITLE = "Where the time went";
const COST_TITLE = "Where the cost went";
const TIME_SUB = "Work and waits, longest first. Select a row, a box, an arrow or a timeline mark.";
const COST_SUB = "Estimated cost, most expensive first. Select a row to see its token breakdown.";
const nodeLabel = (n: FlowNode) => (n.agents.length > 1 ? `${n.label}: ${n.agents.length} sessions` : n.label);

interface Rank {
  label: string;
  value: number;
  shown: string;
  tone?: Severity;
  select?: { kind: SelectionKind; id: string };
}

function Ranking({ title, rows, first }: { title: string; rows: Rank[]; first: boolean }) {
  const sel = useSelection();
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const max = sorted[0]?.value || 1;
  return (
    <section>
      <h3 className={first ? styles.lead : styles.kicker}>{title}</h3>
      {first ? <p className={styles.sub}>{title === TIME_TITLE ? TIME_SUB : COST_SUB}</p> : null}
      {sorted.length === 0 ? <p className={styles.muted}>Nothing known yet.</p> : null}
      <ol className={styles.list}>
        {sorted.map((r) => (
          <li key={r.label}>
            <button type="button" className={styles.rank} data-value={r.value} disabled={!r.select}
                    onClick={() => r.select && sel.select(r.select)}>
              <span className={styles.rankLabel}>{r.label}</span>
              <span className={`${styles.rankNum} ${r.tone ? styles[`fg_${r.tone}`] ?? "" : ""}`}>{r.shown}</span>
              <span className={styles.track} aria-hidden="true">
                <span className={`${styles.fill} ${r.tone ? styles[`bg_${r.tone}`] ?? "" : ""}`}
                      style={{ width: `${Math.round((r.value / max) * 100)}%` }} />
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Overview({ data }: { data: FlowData }) {
  const sel = useSelection();
  const time: Rank[] = [
    ...data.nodes.filter((n) => n.work_s !== null && n.work_s > 0)
      .map((n) => ({ label: nodeLabel(n), value: n.work_s!, shown: fmtDuration(n.work_s), select: { kind: SelectionKind.Node, id: n.id } })),
    ...data.edges.filter((e) => e.wait_s !== null && e.wait_s > 0).map((e) => ({
      label: `Wait: ${e.from} → ${e.to.join(", ")}`, value: e.wait_s!, shown: fmtDuration(e.wait_s),
      select: { kind: SelectionKind.Edge, id: e.id },
    })),
  ];
  const cost: Rank[] = data.nodes.filter((n) => n.cost !== null && n.cost > 0)
    .map((n) => ({ label: n.label, value: n.cost!, shown: fmtCost(n.cost), select: { kind: SelectionKind.Node, id: n.id } }));
  if (data.totals.unattributed_cost) {
    cost.push({ label: UNATTRIBUTED_LABEL, value: data.totals.unattributed_cost, shown: fmtCost(data.totals.unattributed_cost) });
  }
  const costFirst = sel.lens === Lens.Cost;
  const lists = [
    <Ranking key="t" title={TIME_TITLE} rows={time} first={!costFirst} />,
    <Ranking key="c" title={COST_TITLE} rows={cost} first={costFirst} />,
  ];
  return (
    <>
      <p className={styles.kicker}>{OVERVIEW}</p>
      {costFirst ? lists.reverse() : lists}
    </>
  );
}

function TokenRows({ tokens }: { tokens: Tokens | null }) {
  const rows: [string, number | null][] = [
    ["Input", tokens?.input ?? null],
    ["Output", tokens?.output ?? null],
    ["Cache read", tokens?.cache_read ?? null],
    ["Cache write", tokens?.cache_write ?? null],
  ];
  return (
    <dl className={styles.facts}>
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{fmtCount(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function EventList({ title, events, counted = false }: { title: string; events: FlowEvent[]; counted?: boolean }) {
  const sel = useSelection();
  if (!events.length) return null;
  return (
    <section>
      <h3 className={`${styles.kicker} ${styles.listHead}`}>{title}{counted ? ` (${events.length})` : ""}</h3>
      <ol className={styles.list}>
        {events.map((e) => (
          <li key={e.id}>
            <button type="button" className={styles.eventRow}
                    aria-pressed={sel.selection?.kind === SelectionKind.Event && sel.selection.id === e.id}
                    onClick={() => sel.select({ kind: SelectionKind.Event, id: e.id })}>
              <span className={styles.rankNum}>{clock(e.ts)}</span>
              <span className={styles.evText}>
                <span className={styles[`fg_${e.severity}`]}>{e.title}</span>
                <span className={styles.evSub}>
                  {e.from ?? e.from_node ?? "?"} → {e.to ?? e.to_node ?? "?"} · {fmtTokens(tokenSum(e.tokens))} tok · {fmtCost(e.cost)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

function NodeDetail({ data, node }: { data: FlowData; node: FlowNode }) {
  const sel = useSelection();
  const share = node.cost !== null && data.totals.cost ? Math.round((node.cost / data.totals.cost) * 100) : null;
  const roles = Object.entries(node.agents.reduce<Record<string, number>>((m, a) => {
    const role = a.name.split("-")[0] ?? a.name;   // agent names are role-task, e.g. qa-t-0003
    m[role] = (m[role] ?? 0) + 1;
    return m;
  }, {}));
  return (
    <>
      <p className={styles.kicker}>Box · {sel.lens === Lens.Cost ? "cost" : "work"}</p>
      <h2 className={styles.title}>{node.label} · {sel.lens === Lens.Cost ? fmtCost(node.cost) : fmtDuration(node.work_s)}</h2>
      {roles.length ? <p className={styles.routeLine}>{roles.map(([r, n]) => `${r} × ${n}`).join(" · ")}</p> : null}
      <dl className={`${styles.facts} ${styles.table}`}>
        <div><dt>Work</dt><dd>{fmtDuration(node.work_s)}</dd></div>
        <div><dt>Cost</dt><dd title={node.cost_note ?? undefined}>{fmtCost(node.cost)}{share !== null ? ` (${share}%)` : ""}</dd></div>
        <div><dt>Tokens</dt><dd>{fmtTokens(tokenSum(node.tokens))}</dd></div>
      </dl>
      {node.cost_note ? <p className={styles.note}>{node.cost_note}</p> : null}
      <TokenRows tokens={node.tokens} />
      {node.agents.length ? (
        <section>
          <h3 className={`${styles.kicker} ${styles.listHead}`}>Agents</h3>
          <ul className={styles.list}>
            {node.agents.map((a) => (
              <li key={a.name} className={styles.agent} data-agent={a.name}>
                <span className={styles.agentName}>{a.name}</span>
                <span className={styles.rankNum}>{fmtDuration(a.work_s)} · {fmtCost(a.cost)}</span>
                {data.scope === Scope.Goal && a.task_id ? <a className={styles.taskLink} href={`/task/${encodeURIComponent(a.task_id)}`}>Open task flow</a> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <EventList title="Events" counted events={data.events.filter((e) => sel.hot.events.has(e.id))} />
    </>
  );
}

function EdgeDetail({ data, edge, onOpenInstructions }: { data: FlowData; edge: FlowEdge; onOpenInstructions: (e: string) => void }) {
  const evs = data.events.filter((e) => e.edge === edge.id);
  const n = evs.filter((e) => e.is_instruction).length;
  return (
    <>
      <p className={styles.kicker}>Arrow · {edge.label}</p>
      <h2 className={styles.title}>{edge.from} → {edge.to.join(", ")}</h2>
      <dl className={`${styles.facts} ${styles.table}`}>
        <div><dt>Wait</dt><dd>{edge.wait_s === null ? "not a wait" : fmtDuration(edge.wait_s)}</dd></div>
        <div><dt>Forward</dt><dd>{edge.counts.forward}</dd></div>
        <div><dt>Back</dt><dd>{edge.counts.back}</dd></div>
      </dl>
      {n ? <button type="button" className={`${styles.action} ${styles.wideAction}`} onClick={() => onOpenInstructions(edge.id)}>View instructions ({n})</button> : null}
      <EventList title="Events" counted events={evs} />
    </>
  );
}

function EventDetail({ data, ev, onOpenInstructions }: {
  data: FlowData;
  ev: FlowEvent;
  onOpenInstructions: (edgeId: string, eventId?: string) => void;
}) {
  const ordered = timeOrder(data.events);
  const i = ordered.findIndex((e) => e.id === ev.id);
  const around = ordered.slice(Math.max(0, i - AROUND), i).concat(ordered.slice(i + 1, i + 1 + AROUND));
  return (
    <>
      <p className={styles.kicker}>Event {i + 1} of {ordered.length} · {clock(ev.ts)}</p>
      <h2 className={styles.title}>{ev.title}</h2>
      <p className={styles.routeLine}>{ev.from ?? ev.from_node ?? "?"} → {ev.to ?? ev.to_node ?? "?"}</p>
      <dl className={`${styles.facts} ${styles.table}`}>
        <div><dt>Route</dt><dd>{route(ev)}</dd></div>
        <div><dt>Time</dt><dd>{ev.ts} (+{fmtDuration(ev.t_s)})</dd></div>
        <div><dt>Tokens</dt><dd>{fmtTokens(tokenSum(ev.tokens))}</dd></div>
        <div><dt>Cost</dt><dd>{fmtCost(ev.cost)}</dd></div>
      </dl>
      {!ev.cost_exact && ev.cost_note ? <p className={styles.note} data-testid="flow-cost-note">{ev.cost_note}</p> : null}
      {ev.is_instruction && ev.edge ? (
        <button type="button" className={`${styles.action} ${styles.wideAction}`} onClick={() => onOpenInstructions(ev.edge!, ev.id)}>Open in instruction viewer</button>
      ) : null}
      <section className={styles.bodyBox} aria-label="Text">
        <Body showText={data.show_text} html={ev.body_html} />
      </section>
      <EventList title="Around this event" events={around} />
    </>
  );
}

export function Inspector({ data, onOpenInstructions = noop }: {
  data: FlowData;
  onOpenInstructions?: (edgeId: string, eventId?: string) => void;
}) {
  const sel = useSelection();
  const s = sel.selection;
  let body = <Overview data={data} />;
  if (s?.kind === SelectionKind.Node) {
    const node = data.nodes.find((n) => n.id === s.id);
    if (node) body = <NodeDetail data={data} node={node} />;
  } else if (s?.kind === SelectionKind.Edge) {
    const edge = data.edges.find((e) => e.id === s.id);
    if (edge) body = <EdgeDetail data={data} edge={edge} onOpenInstructions={onOpenInstructions} />;
  } else if (s?.kind === SelectionKind.Event) {
    const ev = data.events.find((e) => e.id === s.id);
    if (ev) body = <EventDetail data={data} ev={ev} onOpenInstructions={onOpenInstructions} />;
  }
  return (
    <div className={styles.panel}>
      {sel.notice ? <p className={styles.note} role="status">{sel.notice}</p> : null}
      {s ? (
        <div className={styles.refbar}>
          <RefChip data={data} selection={s} />
          <CopyReference data={data} selection={s} />
        </div>
      ) : null}
      {body}
    </div>
  );
}
