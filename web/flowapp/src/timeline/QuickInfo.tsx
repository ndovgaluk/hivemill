// HM-19: a small popover next to a clicked Lanes mark: what the event is, and what its shape and colour mean.
import { useEffect, useRef } from "react";

import { EventKind, Severity } from "../constants";
import { fmtCost, fmtTokens } from "../format";
import { nodeLabel } from "../groups";
import { tokenSum } from "../inspector/SummaryBar";
import type { FlowData, FlowEvent } from "../types";
import { clock } from "./time";
import styles from "./timeline.module.css";

export const QUICK_INFO = "Quick info";
const ESCAPE = "Escape";

/** Mark shape per event kind, with what it stands for (shapes from timeline.module.css .msg/.status/.verdict). */
export const KIND_INFO: Record<EventKind, { name: string; shape: string; means: string }> = {
  [EventKind.Msg]: { name: "Message", shape: "Small circle",
    means: "a message between agents (request, report, decision, escalation)." },
  [EventKind.Status]: { name: "Status update", shape: "Square",
    means: "something that happened: an agent started or ended, a PR opened, a merge, a gate log line, a task spec." },
  [EventKind.Verdict]: { name: "Verdict", shape: "Large circle", means: "a reviewer, QA or judge verdict on a PR." },
};

/** Mark colour per severity; a passing verdict is green, any other ok mark grey. */
export function colourInfo(e: FlowEvent): string {
  if (e.severity === Severity.Bad) return e.kind === EventKind.Verdict ? "Red: a failing verdict (a rejection)." : "Red: a failure.";
  if (e.severity === Severity.Warn) return "Amber: needs attention (for example an escalation or a stop).";
  return e.kind === EventKind.Verdict ? "Green: a passing verdict." : "Grey: normal.";
}

const labelOf = (data: FlowData, id: string | null) => (id ? nodeLabel(data, id) : null);
const who = (data: FlowData, agent: string | null, node: string | null) =>
  [agent ?? "unknown", labelOf(data, node)].filter(Boolean).join(" · ");

export function QuickInfo({ data, ev, at, onClose }: {
  data: FlowData;
  ev: FlowEvent;
  at: { x: number; y: number; mark?: HTMLElement };   // viewport point under the mark, and the mark itself
  onClose: () => void;
}) {
  const markRef = useRef(at.mark);
  markRef.current = at.mark;
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === ESCAPE) closeRef.current();
    };
    const onDown = (e: MouseEvent) => {
      // a press on its own mark is left to the mark's click (which closes it and clears the selection)
      const t = e.target as Node;
      if (ref.current && !ref.current.contains(t) && !markRef.current?.contains(t)) closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, []);

  const k = KIND_INFO[ev.kind];
  // keep it on screen: open below the mark, flipped above when there is no room
  const W = 320;
  const left = Math.max(8, Math.min(at.x - W / 2, window.innerWidth - W - 8));
  const below = at.y + 14 + 220 < window.innerHeight;
  const style = below ? { left, top: at.y + 14, width: W } : { left, bottom: window.innerHeight - at.y + 14, width: W };
  return (
    <div ref={ref} className={styles.quick} style={style} role="dialog" aria-label={QUICK_INFO} tabIndex={-1}
         data-testid="flow-quick-info">
      <div className={styles.quickHead}>
        <span className={`${styles.mark} ${styles.swatch} ${styles[ev.kind] ?? ""} ${styles[ev.severity] ?? ""}`} aria-hidden="true" />
        <strong>{k.name}</strong>
        <button type="button" className={styles.quickClose} aria-label="Close" onClick={onClose}>×</button>
      </div>
      <p className={styles.quickTitle}>{ev.title}</p>
      <p className={styles.quickMeta}>{who(data, ev.from, ev.from_node)} → {who(data, ev.to, ev.to_node)}</p>
      <p className={styles.quickMeta}>{clock(ev.ts)} · {fmtTokens(tokenSum(ev.tokens))} tok · {fmtCost(ev.cost)}</p>
      <p className={styles.quickWhat}><b>{k.shape}</b>: {k.means} {colourInfo(ev)}</p>
    </div>
  );
}
