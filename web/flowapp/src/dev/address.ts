// Dev page: the goal or task comes from the address (?scope=goal&id=G-001, or ?fixture=goal) instead of the Python page.
import { DevParam, FIXTURE_ID, MountAttr, SCOPES, Scope } from "../constants";

const isScope = (s: string | null): s is Scope => s !== null && (SCOPES as string[]).includes(s);

/** Puts scope and id on the mount element and returns true, or replaces its content with a short form and returns false. */
export function applyAddress(el: HTMLElement, search: string): boolean {
  const q = new URLSearchParams(search);
  const fixture = q.get(DevParam.Fixture);
  const scope = isScope(fixture) ? fixture : q.get(DevParam.Scope);
  const id = isScope(fixture) ? FIXTURE_ID : q.get(DevParam.Id);
  if (isScope(scope) && id) {
    el.setAttribute(MountAttr.Scope, scope);
    el.setAttribute(MountAttr.Id, id);
    return true;
  }
  const form = document.createElement("form");
  form.method = "get";
  const select = document.createElement("select");
  select.name = DevParam.Scope;
  for (const s of SCOPES) select.append(new Option(s, s));
  const input = document.createElement("input");
  input.name = DevParam.Id;
  input.placeholder = "G-001 or T-0003";
  input.required = true;
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Show flow";
  const hint = document.createElement("p");
  hint.textContent = `Pick a goal or task, or open ?${DevParam.Fixture}=${Scope.Goal} for the sample data.`;
  form.append(select, input, button, hint);
  el.replaceChildren(form);
  return false;
}
