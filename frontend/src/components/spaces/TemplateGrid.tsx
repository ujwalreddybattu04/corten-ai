"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { spacesApi } from "@/lib/spacesApi";
import type { SpaceTemplate } from "@/lib/spaceTemplates";
import { SpaceIcon } from "./SpaceVisuals";

/** Template cards; choosing one creates a Space with its instructions and opens it. */
export default function TemplateGrid({ templates }: { templates: SpaceTemplate[] }) {
    const router = useRouter();
    const [creating, setCreating] = useState("");
    const [error, setError] = useState("");
    const use = async (template: SpaceTemplate) => {
        if (creating) return;
        setCreating(template.id);
        setError("");
        try {
            const space = await spacesApi.create({ name: template.name, description: template.description, icon: template.icon,
                instructions: template.instructions });
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
                {templates.map(template => (
                    <button key={template.id} type="button" className="sv-template" disabled={!!creating}
                        aria-busy={creating === template.id} onClick={() => void use(template)}>
                        <SpaceIcon icon={template.icon} size={36} />
                        <span className="sv-template-text">
                            <span className="sv-template-name">{template.name}</span>
                            <span className="sv-template-desc">{template.description}</span>
                        </span>
                        {creating === template.id && <Loader2 size={15} className="sx-spin sv-template-busy" aria-label="Creating" />}
                    </button>
                ))}
            </div>
        </>
    );
}
