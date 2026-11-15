// HM-50: which workflow the diagram shows (name, how it was picked, CI mode, run state), and the engine run's children.
import { WorkflowKind } from "../constants";
import type { FlowData } from "../types";
import styles from "./diagram.module.css";

export const OLD_WORKFLOW = "old workflow";
const ROUND = (n: number) => `${n} fix round${n === 1 ? "" : "s"}`;

/** "huge (chosen) · CI none: no PR, no tests · run building", or "old workflow". */
export function workflowText(data: FlowData): string {
  const w = data.workflow;
  if (!w || w.kind === WorkflowKind.Old) return [OLD_WORKFLOW, w?.note].filter(Boolean).join(" · ");
  return [
    `${w.kind}${w.origin ? ` (${w.origin})` : ""}`,
    w.ci ? `CI ${w.ci}${w.ci_text ? `: ${w.ci_text}` : ""}` : null,
    w.state ? `run ${w.state}` : null,
    w.note,
  ].filter(Boolean).join(" · ");
}

export function WorkflowLine({ data }: { data: FlowData }) {
  return <span className={styles.workflow} data-testid="flow-workflow">Workflow: {workflowText(data)}</span>;
}

/** The story run's children with their state and fix rounds; nothing for the old workflow. */
export function Children({ data }: { data: FlowData }) {
  const kids = data.children ?? [];
  if (!kids.length) return null;
  return (
    <section className={styles.children} aria-label="Children">
      <h3 className={styles.childrenHead}>Children (Builder ⇄ Reviewer){data.workflow?.story ? ` of ${data.workflow.story}` : ""}</h3>
      <ul className={styles.childList}>
        {kids.map((c) => (
          <li key={c.key} data-testid={`flow-child-${c.key}`} data-state={c.state}>
            <span className={styles.childKey}>{c.key}</span> {c.state} · {ROUND(c.rounds)}
          </li>
        ))}
      </ul>
    </section>
  );
}
