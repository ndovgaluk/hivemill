// Every enum-like value of the flow JSON contract (DVDG-551 "Shared contract"; Python side: web/flow.py).
// Use the members (NodeId.Coders), never the string literals.

const values = <T extends Record<string, string>>(o: T) => Object.values(o) as T[keyof T][];

export const Scope = { Goal: "goal", Task: "task" } as const;
export type Scope = (typeof Scope)[keyof typeof Scope];
export const SCOPES = values(Scope);

export const NodeId = {
  Boss: "boss",
  Director: "director",
  Lead: "lead",
  System: "system",
  Pm: "pm",
  Coders: "coders",
  Gate: "gate",
  Judge: "judge",
  Main: "main",
  Wait: "wait",
} as const;
export type NodeId = (typeof NodeId)[keyof typeof NodeId];

export const EdgeId = {
  BossDirector: "bd",
  DirectorLead: "dl",
  SystemLead: "sl",
  Bus: "bus",
  PmCoders: "pc",
  CodersGate: "cg",
  GateJudge: "gj",
  JudgeMain: "jm",
  Rework: "rw",
} as const;
export type EdgeId = (typeof EdgeId)[keyof typeof EdgeId];

export const LaneId = {
  Boss: "boss",
  Director: "director",
  System: "system",
  Lead: "lead",
  Pm: "pm",
  Coders: "coders",
  Reviewer: "reviewer",
  Qa: "qa",
  Judge: "judge",
} as const;
export type LaneId = (typeof LaneId)[keyof typeof LaneId];

export const NodeState = { Done: "done", Live: "live", Fail: "fail", Idle: "idle", Pending: "pending" } as const;
export type NodeState = (typeof NodeState)[keyof typeof NodeState];

export const Severity = { Ok: "ok", Warn: "warn", Bad: "bad" } as const;
export type Severity = (typeof Severity)[keyof typeof Severity];

export const SpanKind = { Work: "work", Wait: "wait", Fail: "fail" } as const;
export type SpanKind = (typeof SpanKind)[keyof typeof SpanKind];

export const EventKind = { Msg: "msg", Status: "status", Verdict: "verdict" } as const;
export type EventKind = (typeof EventKind)[keyof typeof EventKind];

export const SourceTable = { Messages: "messages", Verdicts: "verdicts", Events: "events", Tasks: "tasks" } as const;
export type SourceTable = (typeof SourceTable)[keyof typeof SourceTable];

export const FindingTarget = { Node: "node", Edge: "edge", Event: "event" } as const;
export type FindingTarget = (typeof FindingTarget)[keyof typeof FindingTarget];

export const SelectionKind = { Node: "node", Edge: "edge", Event: "event" } as const;
export type SelectionKind = (typeof SelectionKind)[keyof typeof SelectionKind];

export const Lens = { Time: "time", Cost: "cost" } as const;
export type Lens = (typeof Lens)[keyof typeof Lens];

/** Edge direction along `from → to`. */
export const Dir = { Forward: 1, Back: -1 } as const;
export type Dir = (typeof Dir)[keyof typeof Dir];

export const Region = { Summary: "summary", Diagram: "diagram", Timeline: "timeline", Inspector: "inspector" } as const;
export type Region = (typeof Region)[keyof typeof Region];

export const TimelineTab = { Lanes: "lanes", Sequence: "sequence" } as const;
export type TimelineTab = (typeof TimelineTab)[keyof typeof TimelineTab];

/** Address parameters mirroring the view (DVDG-564): ?sel=V12 | box:coders | arrow:rw, &tab=lanes, &lens=time. */
export const UrlParam = { Sel: "sel", Tab: "tab", Lens: "lens" } as const;
export const RefPrefix = { Box: "box:", Arrow: "arrow:" } as const;
/** Keyboard shortcut on the focused diagram: copy the reference of the current selection. */
export const COPY_KEY = "c";

export const DialogKind ={ Instructions: "instructions", Findings: "findings", Events: "events" } as const;
export type DialogKind = (typeof DialogKind)[keyof typeof DialogKind];

export const LoadStatus = { Loading: "loading", Ready: "ready", Error: "error" } as const;
export type LoadStatus = (typeof LoadStatus)[keyof typeof LoadStatus];

/** The element the Python page renders (with the no-JavaScript SVG flow inside, replaced on mount). */
export const MOUNT_ID = "flow-root";
export const MountAttr = { Scope: "data-scope", Id: "data-id" } as const;

/** Grilling DVDG-552 Q5: poll every 30 s, paused while the tab is hidden. */
export const POLL_MS = 30_000;

// ── development page only (DVDG-563): `npm run dev`; nothing below reaches the committed bundle's behaviour ──
export const DEV_PORT = 5180;
export const DEFAULT_FACTORY_URL = "http://127.0.0.1:18624";
/** `?fixture=goal` loads src/fixtures/goal.json through /api/flow/goal/fixture.json (dev middleware). */
export const FIXTURE_ID = "fixture";
export const DevParam = { Scope: "scope", Id: "id", Fixture: "fixture" } as const;
export const DevEnv = {
  FactoryUrl: "VITE_FACTORY_URL",
  AgentationEndpoint: "VITE_AGENTATION_ENDPOINT",
  AgentationMode: "VITE_AGENTATION_MODE",
} as const;
export const AgentationMode = { Live: "live", Copy: "copy" } as const;
export type AgentationMode = (typeof AgentationMode)[keyof typeof AgentationMode];
/** agentation-mcp's default port; the coding agent reads the annotations from it over MCP. */
export const AGENTATION_ENDPOINT = "http://localhost:4747";

export const flowUrl =(scope: Scope, id: string) => `/api/flow/${scope}/${encodeURIComponent(id)}.json`;
