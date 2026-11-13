// Entry of /static/flow/flow.js: mounts on #flow-root, replacing the server-rendered SVG fallback inside it.
import "@xyflow/react/dist/style.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { MOUNT_ID, MountAttr } from "./constants";
import { DevTools } from "./dev/DevTools";
import { readTarget } from "./useFlowData";

const root = document.getElementById(MOUNT_ID);
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App target={readTarget(root, MountAttr.Scope, MountAttr.Id)} />
      <DevTools />
    </StrictMode>,
  );
}
