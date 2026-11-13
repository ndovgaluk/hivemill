import { lazy, Suspense } from "react";

// import.meta.env.DEV is a build-time constant: the production build drops the import and the agentation package.
const Toolbar = import.meta.env.DEV ? lazy(() => import("./AgentationToolbar")) : null;

export function DevTools() {
  return Toolbar ? (
    <Suspense fallback={null}>
      <Toolbar />
    </Suspense>
  ) : null;
}
