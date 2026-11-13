// The timeline region: Lanes and Sequence tabs, Prev/Next event, expand/collapse, zoom and a legend.
import { useCallback, useEffect, useState } from "react";

import { SelectionKind, TimelineTab } from "../constants";
import { timeOrder, useSelection } from "../selection";
import type { FlowData } from "../types";
import { Lanes } from "./Lanes";
import { Sequence } from "./Sequence";
import { ZOOMS } from "./time";
import styles from "./timeline.module.css";

const noop = () => {};

function useToggleSet() {
  const [set, setSet] = useState<Set<string>>(() => new Set());
  const toggle = useCallback((id: string, open?: boolean) => {
    setSet((prev) => {
      const want = open ?? !prev.has(id);
      if (want === prev.has(id)) return prev;
      const next = new Set(prev);
      if (want) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);
  return [set, toggle, setSet] as const;
}

export interface ExpandRequest {
  node: string;
  n: number;
}

export function Timeline({ data, onOpenInstructions = noop, expand = null }: {
  data: FlowData;
  onOpenInstructions?: (edgeId: string, eventId: string) => void;
  /** "Expand on timeline" from a diagram box: show Lanes and open that box's lanes. */
  expand?: ExpandRequest | null;
}) {
  const sel = useSelection();
  const tab = sel.tab;            // in the store, so the address can mirror it (DVDG-564)
  const setTab = sel.setTab;
  const [zoomI, setZoomI] = useState(0);
  const [lanesOpen, toggleLane, setLanes] = useToggleSet();
  const [phasesOpen, togglePhase, setPhases] = useToggleSet();

  useEffect(() => {
    if (!expand) return;
    setTab(TimelineTab.Lanes);
    for (const l of data.lanes) if (l.node === expand.node && l.rows.length) toggleLane(l.id, true);
  }, [expand, data.lanes, setTab, toggleLane]);

  const ordered = timeOrder(data.events);
  const pos = sel.selection?.kind === SelectionKind.Event ? ordered.findIndex((e) => e.id === sel.selection?.id) + 1 : 0;
  const allOpen = tab === TimelineTab.Lanes
    ? data.lanes.filter((l) => l.rows.length).every((l) => lanesOpen.has(l.id))
    : data.phases.every((p) => phasesOpen.has(p.id));
  const expandAll = (open: boolean) => {
    if (tab === TimelineTab.Lanes) setLanes(new Set(open ? data.lanes.filter((l) => l.rows.length).map((l) => l.id) : []));
    else setPhases(new Set(open ? data.phases.map((p) => p.id) : []));
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h3 className={styles.heading}>Timeline</h3>
        <span role="group" aria-label="Timeline view" className={styles.segmented}>
          <button type="button" aria-pressed={tab === TimelineTab.Lanes} onClick={() => setTab(TimelineTab.Lanes)}>Lanes</button>
          <button type="button" aria-pressed={tab === TimelineTab.Sequence} onClick={() => setTab(TimelineTab.Sequence)}>Sequence</button>
        </span>
        <span className={styles.group}>
          <button type="button" onClick={sel.stepPrev}>Prev event</button>
          <span data-testid="flow-position">{pos ? `${pos} / ${ordered.length}` : `– / ${ordered.length}`}</span>
          <button type="button" onClick={sel.stepNext}>Next event</button>
        </span>
        <button type="button" onClick={() => expandAll(!allOpen)}>{allOpen ? "Collapse all" : "Expand all"}</button>
        {tab === TimelineTab.Lanes ? (
          <span className={styles.group}>
            <button type="button" aria-label="Timeline zoom out" onClick={() => setZoomI((i) => Math.max(0, i - 1))}>−</button>
            <span data-testid="flow-timeline-zoom">{ZOOMS[zoomI]}x</span>
            <button type="button" aria-label="Timeline zoom in" onClick={() => setZoomI((i) => Math.min(ZOOMS.length - 1, i + 1))}>+</button>
          </span>
        ) : null}
        <span className={styles.legend} aria-label="Legend">
          <span><span className={`${styles.key} ${styles.work}`} /> work</span>
          <span><span className={`${styles.key} ${styles.wait}`} /> queued</span>
          <span><span className={`${styles.key} ${styles.fail}`} /> ended in FAIL</span>
          <span><span className={`${styles.mk}`} /> message</span>
          <span><span className={`${styles.mk} ${styles.mk_status}`} /> status</span>
          <span><span className={`${styles.mk} ${styles.mk_verdict}`}>✓</span> verdict</span>
        </span>
      </div>
      {tab === TimelineTab.Lanes ? (
        <Lanes data={data} zoom={ZOOMS[zoomI]!} expanded={lanesOpen} toggle={toggleLane} />
      ) : (
        <Sequence data={data} open={phasesOpen} toggle={togglePhase} onOpenInstructions={onOpenInstructions} />
      )}
    </div>
  );
}
