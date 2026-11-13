import { AGENTATION_ENDPOINT, AgentationMode, DevEnv } from "../constants";

/** Props for the Agentation toolbar: live sync to the MCP server by default, local copy-and-paste with the copy mode. */
export function toolbarProps(env: Record<string, string | boolean | undefined>): { endpoint?: string } {
  if (env[DevEnv.AgentationMode] === AgentationMode.Copy) return {};
  const override = env[DevEnv.AgentationEndpoint];
  return { endpoint: typeof override === "string" && override ? override : AGENTATION_ENDPOINT };
}
