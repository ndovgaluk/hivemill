// Dialog shell for every dialog: labelled role=dialog, backdrop, focus trap, Escape, focus back to the opener.
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import styles from "./instructions.module.css";

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
const ESCAPE = "Escape";
const TAB = "Tab";

// HM-14: open dialogs, newest last; Escape anywhere on the page closes only the top one
const openStack: string[] = [];

export function Dialog({ title, onClose, children, wide = false, aside }: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  aside?: ReactNode;   // a short note next to Close, e.g. "3 on this link"
}) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    ref.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => (opener.current as HTMLElement | null)?.focus?.();
  }, []);

  // Escape is caught on the document, not only on the dialog: after a click on plain text inside it focus sits on
  // the body and a dialog-level handler never sees the key
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    openStack.push(id);
    const onDocKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== ESCAPE || openStack[openStack.length - 1] !== id) return;
      e.stopPropagation();
      closeRef.current();
    };
    document.addEventListener("keydown", onDocKey);
    return () => {
      document.removeEventListener("keydown", onDocKey);
      openStack.splice(openStack.indexOf(id), 1);
    };
  }, [id]);

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== TAB || !ref.current) return;
    const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (!items.length) return;
    const first = items[0]!;
    const last = items[items.length - 1]!;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} className={`${styles.dialog} ${wide ? styles.wide : ""}`}
           onKeyDown={onKey} onClick={(e) => e.stopPropagation()}>
        <header className={styles.head}>
          <h2 id={id} className={styles.title}>{title}</h2>
          {aside ? <span className={styles.aside}>{aside}</span> : null}
          <button type="button" onClick={onClose}>Close</button>
        </header>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
