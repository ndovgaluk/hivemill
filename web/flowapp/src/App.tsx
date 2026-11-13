// The page frame: four named regions (summary bar, diagram, timeline, inspector) and the dialogs they open.
import { LoadStatus, Region } from "./constants";
import { Diagram } from "./diagram/Diagram";
import { Inspector } from "./inspector/Inspector";
import { SummaryBar } from "./inspector/SummaryBar";
import { useCallback, useState } from "react";

import { DialogsProvider, useDialogs } from "./instructions/Dialogs";
import { Timeline, type ExpandRequest } from "./timeline/Timeline";
import styles from "./App.module.css";
import { SelectionProvider } from "./selection";
import type { FlowData } from "./types";
import { useFlowData, type Target } from "./useFlowData";

function Frame({ data }: { data: FlowData }) {
  const dialogs = useDialogs();
  // "Expand on timeline" on a box: the timeline opens that box's lanes (n makes a repeat click count again)
  const [expand, setExpand] = useState<ExpandRequest | null>(null);
  const onExpandLanes = useCallback((node: string) => setExpand((p) => ({ node, n: (p?.n ?? 0) + 1 })), []);
  return (
    <div className={styles.frame}>
      <section className={`${styles.card} ${styles.summary}`} data-region={Region.Summary} aria-label="Summary">
        <SummaryBar data={data} onOpenRejections={dialogs.openRejections} />
      </section>
      <div className={styles.main}>
      <section className={`${styles.card} ${styles.diagram}`} data-region={Region.Diagram} aria-label="Diagram">
        <Diagram data={data} onOpenFindings={dialogs.openFindings} onOpenEvents={dialogs.openEvents}
                 onOpenInstructions={dialogs.openInstructions} onExpandLanes={onExpandLanes} />
      </section>
      <section className={`${styles.card} ${styles.timeline}`} data-region={Region.Timeline} aria-label="Timeline">
        <Timeline data={data} onOpenInstructions={dialogs.openInstructions} expand={expand} />
      </section>
      </div>
      <aside className={`${styles.card} ${styles.inspector}`} data-region={Region.Inspector} aria-label="Inspector">
        <Inspector data={data} onOpenInstructions={dialogs.openInstructions} />
      </aside>
    </div>
  );
}

export const LOAD_FAILED = "Flow data could not be loaded";

export function App({ target, pollMs }: { target: Target | null; pollMs?: number }) {
  const load = useFlowData(target, pollMs);
  if (load.status === LoadStatus.Loading) {
    return <p className={styles.note}>Loading the flow…</p>;
  }
  if (load.status === LoadStatus.Error || !load.data) {
    return (
      <div className={styles.error} role="alert">
        <p>{LOAD_FAILED} ({load.error}).</p>
        <button type="button" onClick={load.retry}>Retry</button>
      </div>
    );
  }
  return (
    <SelectionProvider data={load.data}>
      <DialogsProvider data={load.data}>
        <Frame data={load.data} />
      </DialogsProvider>
      {load.error ? <p className={styles.note}>Last refresh failed: {load.error}</p> : null}
    </SelectionProvider>
  );
}
