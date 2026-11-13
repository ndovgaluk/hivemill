// The flow JSON payload (DVDG-551 "Shared contract"). null = unknown, never 0 or a guess.
import type {
  Dir,
  EdgeId,
  EventKind,
  FindingTarget,
  LaneId,
  NodeId,
  NodeState,
  Scope,
  Severity,
  SourceTable,
  SpanKind,
} from "./constants";

export interface Tokens {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
}

export interface Totals {
  agent_s: number | null;
  tokens: Tokens | null;
  cost: number | null;
  cost_as_of: string | null;
  cost_note: string | null;
  unattributed_cost: number | null;
  /** Goal scope: HQ, lead and other sessions of the goal without a task. */
  overhead_cost?: number | null;
  rejections: number;
  messages: number;
}

export interface Agent {
  name: string;
  status: string;
  work_s: number | null;
  cost: number | null;
  task_id: string | null;
  session_id: string | null;
  after_last_event: unknown;
}

export interface FlowNode {
  id: NodeId;
  label: string;
  state: NodeState;
  work_s: number | null;
  tokens: Tokens | null;
  cost: number | null;
  cost_note: string | null;
  agents: Agent[];
}

export interface FlowEdge {
  id: EdgeId;
  from: NodeId;
  to: NodeId[];
  label: string;
  wait_s: number | null;
  severity: Severity;
  pending: boolean;
  counts: { forward: number; back: number };
  /** Per task, on the wait edges (pm → coders queue, coders → gate review start). */
  waits: Wait[];
}

export interface Wait {
  task_id: string;
  wait_s: number | null;
  start_s: number | null;
  end_s: number | null;
  open: boolean;
  note: string | null;
}

export interface Span {
  start_s: number | null;
  end_s: number | null;
  kind: SpanKind;
  note: string | null;
}

export interface LaneRow {
  name: string;
  task_id: string | null;
  spans: Span[];
}

export interface Lane {
  id: LaneId;
  node: NodeId;
  label: string;
  rows: LaneRow[];
}

export interface FlowEvent {
  id: string;
  key: string;
  ref: { table: SourceTable; rowid: number };
  task_id: string | null;
  goal_id: string | null;
  t_s: number | null;
  ts: string;
  lane: LaneId | null;
  row: string | null;
  edge: EdgeId | null;
  dir: Dir | null;
  from: string | null;
  to: string | null;
  from_node: NodeId | null;
  to_node: NodeId | null;
  kind: EventKind;
  severity: Severity;
  title: string;
  is_instruction: boolean;
  /** Rendered and escaped by the server's md(); null when text is off. */
  body_html: string | null;
  tokens: Tokens | null;
  cost: number | null;
  cost_note: string | null;
  cost_exact: boolean;
}

export interface Finding {
  severity: Severity;
  text: string;
  target: { kind: FindingTarget; id: string };
  node: NodeId | null;
}

export interface Phase {
  id: string;
  title: string;
  summary: string;
  event_ids: string[];
  span_refs: unknown[];
}

export interface FlowData {
  scope: Scope;
  id: string;
  goal_id: string | null;
  title: string;
  status: string;
  start: string;
  now: string;
  elapsed_s: number | null;
  show_text: boolean;
  totals: Totals;
  nodes: FlowNode[];
  edges: FlowEdge[];
  lanes: Lane[];
  events: FlowEvent[];
  findings: Finding[];
  phases: Phase[];
}
