// Which dialog is open, the three open functions the views call, and the dialogs themselves.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { DialogKind, SelectionKind, type NodeId } from "../constants";
import { fmtCost, fmtTokens } from "../format";
import { timeOrder, useSelection } from "../selection";
import { clock } from "../timeline/time";
import type { FlowData, FlowEvent } from "../types";
import { CopyReference } from "../reference/CopyReference";
import { Body } from "./Body";
import { Dialog } from "./Dialog";
import styles from "./instructions.module.css";

type Open =
  | { kind: typeof DialogKind.Instructions; edgeId: string; eventId?: string }
  | { kind: typeof DialogKind.Findings; nodeId: string }
  | { kind: typeof DialogKind.Events; nodeId: string };

export interface DialogsApi {
  openInstructions: (edgeId: string, eventId?: string) => void;
  openFindings: (nodeId: string) => void;
  openEvents: (nodeId: string) => void;
}

const Ctx = createContext<DialogsApi | null>(null);

export function useDialogs(): DialogsApi {
  const api = useContext(Ctx);
  if (!api) throw new Error("useDialogs outside DialogsProvider");
  return api;
}

const tokenSum = (e: FlowEvent) => (e.tokens ? e.tokens.input + e.tokens.output + e.tokens.cache_read + e.tokens.cache_write : null);

export function DialogsProvider({ data, children }: { data: FlowData; children: ReactNode }) {
  const [open, setOpen] = useState<Open | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const api = useMemo<DialogsApi>(() => ({
    openInstructions: (edgeId, eventId) => setOpen({ kind: DialogKind.Instructions, edgeId, eventId }),
    openFindings: (nodeId) => setOpen({ kind: DialogKind.Findings, nodeId }),
    openEvents: (nodeId) => setOpen({ kind: DialogKind.Events, nodeId }),
  }), []);
  return (
    <Ctx.Provider value={api}>
      {children}
      {open?.kind === DialogKind.Instructions ? <InstructionViewer data={data} edgeId={open.edgeId} eventId={open.eventId} onClose={close} /> : null}
      {open?.kind === DialogKind.Findings ? <FindingsDialog data={data} nodeId={open.nodeId} onClose={close} /> : null}
      {open?.kind === DialogKind.Events ? <EventsDialog data={data} nodeId={open.nodeId} onClose={close} /> : null}
    </Ctx.Provider>
  );
}

export const EVENTS_HINT = "Pick one to read it here; the diagram and timeline follow.";

const labelOf = (data: FlowData, id: string | null | undefined) => data.nodes.find((n) => n.id === id)?.label ?? id ?? "?";

/** The right-hand side of a two-column dialog: who sent what to whom, its cost, its text, and the jump back. */
function EventPreview({ data, ev, onClose }: { data: FlowData; ev: FlowEvent; onClose: () => void }) {
  const sel = useSelection();
  return (
    <article className={styles.pane}>
      <div className={styles.cards}>
        <section className={styles.card} aria-label="From">
          <h3>From</h3>
          <p className={styles.agent}>{ev.from ?? "unknown"}</p>
          <p className={styles.role}>{labelOf(data, ev.from_node)}</p>
        </section>
        <span className={styles.arrow} aria-hidden="true">→</span>
        <section className={`${styles.card} ${styles.cardTo}`} aria-label="To">
          <h3>To</h3>
          <p className={styles.agent}>{ev.to ?? "unknown"}</p>
          <p className={styles.role}>{labelOf(data, ev.to_node)}</p>
        </section>
      </div>
      <div className={styles.subjectRow}>
        <h3 className={styles.subject}>{ev.title}</h3>
        <p className={styles.meta} title={!ev.cost_exact && ev.cost_note ? ev.cost_note : undefined}>
          {clock(ev.ts)} · {fmtTokens(tokenSum(ev))} tok · {fmtCost(ev.cost)}</p>
      </div>
      <div className={styles.bodyBox}><Body showText={data.show_text} html={ev.body_html} /></div>
      <div className={styles.actions}>
        <CopyReference data={data} selection={{ kind: SelectionKind.Event, id: ev.id }} />
        <button type="button" className={styles.primary} onClick={() => {
          sel.select({ kind: SelectionKind.Event, id: ev.id });
          onClose();
        }}>Show on diagram and timeline</button>
      </div>
    </article>
  );
}

/** One row of a dialog's left-hand list: time, tokens and cost, then route and title. */
function EventRow({ e, on, pick }: { e: FlowEvent; on: boolean; pick: (e: FlowEvent) => void }) {
  return (
    <li>
      <button type="button" aria-pressed={on} onClick={() => pick(e)}>
        <span className={styles.meta}>{clock(e.ts)} · {fmtTokens(tokenSum(e))} tok · {fmtCost(e.cost)}</span>
        <span className={styles.who}>{e.from ?? e.from_node ?? "?"} → {e.to ?? e.to_node ?? "?"}</span>
        <span className={styles.what}>{e.title}</span>
      </button>
    </li>
  );
}

function InstructionViewer({ data, edgeId, eventId, onClose }: { data: FlowData; edgeId: string; eventId?: string; onClose: () => void }) {
  const sel = useSelection();
  const edge = data.edges.find((e) => e.id === edgeId);
  const items = timeOrder(data.events.filter((e) => e.edge === edgeId && e.is_instruction));
  const [activeId, setActiveId] = useState(eventId ?? items[0]?.id);
  const active = items.find((e) => e.id === activeId) ?? items[0];
  const title = `Instructions: ${labelOf(data, edge?.from)} → ${(edge?.to ?? []).map((t) => labelOf(data, t)).join(", ")}`
    + (edge ? `: ${edge.label}` : "");
  const pick = (e: FlowEvent) => {
    setActiveId(e.id);
    sel.select({ kind: SelectionKind.Event, id: e.id });
  };
  return (
    <Dialog title={title} onClose={onClose} wide aside={`${items.length} on this link`}>
      <div className={styles.viewer}>
        <ol className={styles.list} aria-label="Instructions on this link">
          {items.map((e) => <EventRow key={e.id} e={e} on={e.id === active?.id} pick={pick} />)}
        </ol>
        {active ? <EventPreview data={data} ev={active} onClose={onClose} />
          : <p className={styles.muted}>No instructions on this link.</p>}
      </div>
    </Dialog>
  );
}

function FindingsDialog({ data, nodeId, onClose }: { data: FlowData; nodeId: string; onClose: () => void }) {
  const sel = useSelection();
  const list = data.findings.filter((f) => f.node === (nodeId as NodeId));
  return (
    <Dialog title={`Findings: ${labelOf(data, nodeId)}`} onClose={onClose}>
      <ul className={styles.list}>
        {list.map((f, i) => (
          <li key={i}>
            <button type="button" data-severity={f.severity} onClick={() => {
              sel.select({ kind: f.target.kind, id: f.target.id });
              onClose();
            }}>{f.text}</button>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

function EventsDialog({ data, nodeId, onClose }: { data: FlowData; nodeId: string; onClose: () => void }) {
  const sel = useSelection();
  const list = timeOrder(data.events.filter((e) => e.from_node === nodeId || e.to_node === nodeId));
  // start on the event already selected, when it belongs to this box
  const current = sel.selection?.kind === SelectionKind.Event ? sel.selection.id : undefined;
  const [activeId, setActiveId] = useState(list.some((e) => e.id === current) ? current : list[0]?.id);
  const active = list.find((e) => e.id === activeId) ?? list[0];
  const pick = (e: FlowEvent) => {
    setActiveId(e.id);
    sel.select({ kind: SelectionKind.Event, id: e.id });
  };
  return (
    <Dialog title={`${labelOf(data, nodeId)}: messages and events`} onClose={onClose} wide aside={`${list.length} in time order`}>
      <div className={styles.viewer}>
        <div className={styles.side}>
          <p className={styles.hint}>{EVENTS_HINT}</p>
          <ol className={styles.list} aria-label="Messages and events">
            {list.map((e) => <EventRow key={e.id} e={e} on={e.id === active?.id} pick={pick} />)}
          </ol>
        </div>
        {active ? <EventPreview data={data} ev={active} onClose={onClose} />
          : <p className={styles.muted}>No messages or events for this box.</p>}
      </div>
    </Dialog>
  );
}
