// Instruction text: the server's md() output (escaped first; only http(s) links become anchors), or why it is missing.
import type { MouseEvent } from "react";

import styles from "./instructions.module.css";

export const HIDDEN_TEXT = "Message text is hidden. Set serve_show_text=1 and bind to loopback to show it.";
export const NO_TEXT = "No text for this step.";
const NEW_TAB = "_blank";
const NEW_TAB_FEATURES = "noopener,noreferrer";

/** Links in agent-written text open in a new tab without referrer or opener. */
function openLinksOutside(e: MouseEvent<HTMLDivElement>) {
  const a = (e.target as HTMLElement).closest("a");
  if (!a) return;
  e.preventDefault();
  window.open(a.href, NEW_TAB, NEW_TAB_FEATURES);
}

export function Body({ showText, html }: { showText: boolean; html: string | null }) {
  if (!showText) return <p className={styles.muted}>{HIDDEN_TEXT}</p>;
  if (!html) return <p className={styles.muted}>{NO_TEXT}</p>;
  // rendered and escaped by web/html.py md(); the page CSP forbids any script in it anyway
  return <div className={styles.body} data-testid="flow-body" onClick={openLinksOutside} dangerouslySetInnerHTML={{ __html: html }} />;
}
