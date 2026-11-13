// Totals and the findings as chips; a chip selects its target in every view.
import { fmtCost, fmtDuration, fmtTokens } from "../format";
import { useSelection } from "../selection";
import { Severity } from "../constants";
import type { FlowData, FlowEdge, Tokens } from "../types";
import styles from "./inspector.module.css";

const FINDINGS = "Findings";

export const tokenSum = (t: Tokens | null | undefined) => (t ? t.input + t.output + t.cache_read + t.cache_write : null);

export function SummaryBar({ data }: { data: FlowData }) {
  const sel = useSelection();
  const longest = data.edges.reduce<FlowEdge | null>(
    (a, e) => (e.wait_s !== null && e.wait_s > (a?.wait_s ?? 0) ? e : a), null);
  const kpis: [string, string, Severity?][] = [
    ["Elapsed", fmtDuration(data.elapsed_s)],
    ["Agent time", fmtDuration(data.totals.agent_s)],
    ["Longest wait", fmtDuration(longest?.wait_s ?? null), longest?.severity],
    ["Rejections", String(data.totals.rejections), data.totals.rejections ? Severity.Bad : undefined],
    ["Tokens", fmtTokens(tokenSum(data.totals.tokens))],
    ["Cost (est.)", fmtCost(data.totals.cost)],
  ];
  return (
    <div className={styles.bar}>
      <dl className={styles.kpis}>
        {kpis.map(([k, v, sev]) => (
          <div key={k} className={styles.kpi}>
            <dt>{k}</dt>
            <dd data-kpi={k} className={sev ? styles[`fg_${sev}`] : undefined}>{v}</dd>
          </div>
        ))}
      </dl>
      {data.findings.length ? (
        <div className={styles.findings}>
        <span className={styles.kicker}>{FINDINGS}</span>
        <ul className={styles.chips} aria-label="Findings">
          {data.findings.map((f, i) => (
            <li key={i}>
              <button type="button" className={`${styles.chip} ${styles[f.severity] ?? ""}`} data-severity={f.severity}
                      aria-pressed={sel.selection?.kind === f.target.kind && sel.selection.id === f.target.id}
                      onClick={() => sel.select({ kind: f.target.kind, id: f.target.id })}>
                {f.text}
              </button>
            </li>
          ))}
        </ul>
        </div>
      ) : null}
    </div>
  );
}
