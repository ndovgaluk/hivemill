// Loads /api/flow/{scope}/{id}.json and refreshes it every POLL_MS while the tab is visible.
import { useCallback, useEffect, useState } from "react";

import { LoadStatus, POLL_MS, SCOPES, flowUrl, type Scope } from "./constants";
import type { FlowData } from "./types";

export interface FlowLoad {
  status: LoadStatus;
  data: FlowData | null;
  error: string | null;
  /** Load again now (the error state's Retry). */
  retry: () => void;
}

export interface Target {
  scope: Scope;
  id: string;
}

/** The scope and id the Python page put on the mount element, or null when missing or invalid. */
export function readTarget(el: Element | null, scopeAttr: string, idAttr: string): Target | null {
  const scope = el?.getAttribute(scopeAttr);
  const id = el?.getAttribute(idAttr);
  if (!scope || !id || !(SCOPES as string[]).includes(scope)) return null;
  return { scope: scope as Scope, id };
}

async function fetchFlow(target: Target, signal: AbortSignal): Promise<FlowData> {
  const res = await fetch(flowUrl(target.scope, target.id), { signal, headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  try {
    return (await res.json()) as FlowData;
  } catch {
    throw new Error("invalid JSON");
  }
}

type LoadState = Omit<FlowLoad, "retry">;

export function useFlowData(target: Target | null, pollMs: number = POLL_MS): FlowLoad {
  const [load, setLoad] = useState<LoadState>({ status: LoadStatus.Loading, data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    setLoad((prev) => ({ ...prev, status: prev.data ? prev.status : LoadStatus.Loading }));
    setAttempt((n) => n + 1);
  }, []);
  const scope = target?.scope;
  const id = target?.id;

  useEffect(() => {
    if (!scope || !id) {
      setLoad({ status: LoadStatus.Error, data: null, error: "no goal or task on the page" });
      return;
    }
    const ctrl = new AbortController();
    const run = () => {
      fetchFlow({ scope, id }, ctrl.signal).then(
        (data) => setLoad({ status: LoadStatus.Ready, data, error: null }),
        (e: unknown) => {
          if (ctrl.signal.aborted) return;
          // a failed refresh keeps the last good data on screen
          setLoad((prev) => ({ status: prev.data ? prev.status : LoadStatus.Error, data: prev.data, error: String((e as Error).message ?? e) }));
        },
      );
    };
    run();
    const timer = setInterval(() => {
      if (!document.hidden) run();
    }, pollMs);
    return () => {
      ctrl.abort();
      clearInterval(timer);
    };
  }, [scope, id, pollMs, attempt]);

  return { ...load, retry };
}
