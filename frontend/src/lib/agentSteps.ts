/** A Space agent's visible steps. The server sends each step when it starts and again when it finishes or fails,
 *  with the same id, so the client updates the step where it is instead of adding a duplicate. */
export interface AgentStep {
    type: "agent_step";
    id: string;
    content: string;
    tool: string;
    status: "running" | "done" | "failed";
    detail?: string;
    ms?: number;
}

export function upsertAgentStep<T extends { type: string; id?: string }>(steps: T[], json: Record<string, unknown>): (T | AgentStep)[] {
    if (typeof json.id !== "string" || !json.id) return steps;
    const step: AgentStep = {
        type: "agent_step", id: json.id, content: String(json.label || "Working").slice(0, 200), tool: String(json.tool || ""),
        status: json.status === "done" || json.status === "failed" ? json.status : "running",
        detail: typeof json.detail === "string" && json.detail ? json.detail.slice(0, 200) : undefined,
        ms: typeof json.ms === "number" && Number.isFinite(json.ms) && json.ms >= 0 ? json.ms : undefined,
    };
    const index = steps.findIndex(item => item.type === "agent_step" && item.id === step.id);
    return index === -1 ? [...steps, step] : steps.map((item, i) => (i === index ? step : item));
}
