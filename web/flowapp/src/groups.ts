// HM-17: node groups (the "Review gate" frame around Reviewer and QA). An edge or event may name a group id where a
// box is meant; these helpers turn it into its boxes, or name it.
import type { FlowData, FlowGroup } from "./types";

const groupsOf = (data: FlowData): FlowGroup[] => data.groups ?? [];

/** The boxes an id stands for: a group's members, else the id itself. */
export function members(data: FlowData, id: string): string[] {
  return groupsOf(data).find((g) => g.id === id)?.nodes ?? [id];
}

/** The group a box sits in, or null. */
export function groupOf(data: FlowData, id: string): string | null {
  return groupsOf(data).find((g) => (g.nodes as string[]).includes(id))?.id ?? null;
}

/** A node's or a group's label; the id itself when neither is known. */
export function nodeLabel(data: FlowData, id: string | null | undefined): string {
  if (!id) return "?";
  return data.nodes.find((n) => n.id === id)?.label ?? groupsOf(data).find((g) => g.id === id)?.label ?? id;
}
