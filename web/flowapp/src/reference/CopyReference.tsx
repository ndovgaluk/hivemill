// The "Copy for investigation" button (multi-line reference) and the key chip (one-line qualified key).
import { useEffect, useRef, useState } from "react";

import type { Selection } from "../selection";
import type { FlowData } from "../types";
import styles from "./reference.module.css";
import { buildReference, copyText, qualifiedKey, selParam } from "./reference";

export const COPY_LABEL = "Copy for investigation";
export const COPIED_LABEL = "Copied";
const COPIED_MS = 1500;

function useCopied() {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const flash = () => {
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), COPIED_MS);
  };
  return [copied, flash] as const;
}

/** Fallback when the browser has no clipboard here: the text, focused and selected, for Ctrl+C. */
function Fallback({ text }: { text: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);
  return <textarea ref={ref} className={styles.fallback} readOnly value={text} aria-label="Reference to copy" rows={6} />;
}

export function CopyReference({ data, selection, icon = false }: { data: FlowData; selection: Selection; icon?: boolean }) {
  const [copied, flash] = useCopied();
  const [fallback, setFallback] = useState<string | null>(null);
  const copy = async () => {
    const text = buildReference(data, selection);
    if (await copyText(text)) {
      setFallback(null);
      flash();
    } else setFallback(text);
  };
  return (
    <span className={styles.wrap}>
      <button type="button" className={icon ? styles.icon : styles.button} data-testid="flow-copy-ref"
              aria-label={copied ? COPIED_LABEL : COPY_LABEL} title={COPY_LABEL} onClick={() => void copy()}>
        {icon ? "⧉" : copied ? COPIED_LABEL : COPY_LABEL}
      </button>
      {fallback !== null ? <Fallback text={fallback} /> : null}
    </span>
  );
}

export function RefChip({ data, selection, testId }: { data: FlowData; selection: Selection; testId?: string }) {
  const [copied, flash] = useCopied();
  return (
    <span className={styles.chip} data-testid={testId}>
      <code>{selParam(selection)}</code>
      <button type="button" className={styles.chipCopy} aria-label="Copy reference" title={qualifiedKey(data, selection)}
              onClick={() => void copyText(qualifiedKey(data, selection)).then((ok) => ok && flash())}>
        {copied ? "✓" : "⧉"}
      </button>
    </span>
  );
}
