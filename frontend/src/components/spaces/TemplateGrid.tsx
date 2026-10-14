"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Loader2 } from "lucide-react";
import { spacesApi, type AgentTool } from "@/lib/spacesApi";
import type { TemplateCard } from "@/lib/spaceTemplates";
import { SpaceIcon } from "./SpaceVisuals";

const SHOWN_TOOLS = 2;
// Every agent can search the web and its files; a card leads with what sets its agent apart.
const COMMON_TOOLS = new Set(["web_search", "read_webpage", "search_space_files", "calculator"]);
let toolsRequest: Promise<Record<string, AgentTool[]>> | null = null;

/** Each template's agent tools, specialist ones first, fetched once per page load. Cards render without them meanwhile. */
function templateTools(): Promise<Record<string, AgentTool[]>> {
    toolsRequest ??= spacesApi.templates()
        .then(result => Object.fromEntries(result.items.map(item => [item.id,
            [...item.tools.filter(tool => !COMMON_TOOLS.has(tool.id)), ...item.tools.filter(tool => COMMON_TOOLS.has(tool.id))]])))
        .catch(() => { toolsRequest = null; return {}; });
    return toolsRequest;
}

/** Template cards; choosing one creates a Space whose agent is equipped by that template, then opens it. */
export default function TemplateGrid({ templates }: { templates: TemplateCard[] }) {
    const router = useRouter();
    const [creating, setCreating] = useState("");
    const [error, setError] = useState("");
    const [tools, setTools] = useState<Record<string, AgentTool[]>>({});
    useEffect(() => {
        let live = true;
        void templateTools().then(found => { if (live) setTools(found); });
        return () => { live = false; };
    }, []);
    const use = async (template: TemplateCard) => {
        if (creating) return;
        setCreating(template.id);
        setError("");
        try {
            // The server fills in the template's name, description, icon, instructions and tools.
            const space = await spacesApi.create({ template: template.id });
            router.push(`/spaces/${space.id}`);
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "The Space could not be created. Please retry.");
            setCreating("");
        }
    };
    return (
        <>
            {error && <p className="sx-error" role="alert">{error}</p>}
            <div className="sv-template-grid">
                {templates.map(template => {
                    const equipped = tools[template.id] ?? [];
                    return (
                        <button key={template.id} type="button" className="sv-template" disabled={!!creating}
                            aria-busy={creating === template.id} onClick={() => void use(template)}>
                            <span className="sv-template-top"><SpaceIcon icon={template.icon} size={36} /><span>{template.category}</span></span>
                            <span className="sv-template-text">
                                <span className="sv-template-name">{template.name}</span>
                                <span className="sv-template-desc">{template.description}</span>
                                {equipped.length > 0 && (
                                    <span className="sv-template-tools" aria-label={`Tools: ${equipped.map(tool => tool.label).join(", ")}`}>
                                        {equipped.slice(0, SHOWN_TOOLS).map(tool => <span key={tool.id} className="sv-tool-chip">{tool.label}</span>)}
                                        {equipped.length > SHOWN_TOOLS && <span className="sv-tool-chip sv-tool-more">+{equipped.length - SHOWN_TOOLS}</span>}
                                    </span>
                                )}
                            </span>
                            <span className="sv-template-use">{creating === template.id ? "Creating Space" : "Use template"}<ArrowUpRight size={14} /></span>
                            {creating === template.id && <Loader2 size={15} className="sx-spin sv-template-busy" aria-label="Creating" />}
                        </button>
                    );
                })}
            </div>
        </>
    );
}
