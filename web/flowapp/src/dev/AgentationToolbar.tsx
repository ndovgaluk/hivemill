// Loaded lazily and only in development (DevTools.tsx); never part of web/static/flow/.
import { Agentation } from "agentation";

import { toolbarProps } from "./toolbar";

export default function AgentationToolbar() {
  return <Agentation {...toolbarProps(import.meta.env)} />;
}
