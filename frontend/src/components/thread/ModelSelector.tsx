"use client";

import { AVAILABLE_MODELS } from "@/config/models";
import { Dropdown } from "@/components/ui";

interface ModelSelectorProps {
    value: string;
    onChange: (model: string) => void;
}

export default function ModelSelector({ value, onChange }: ModelSelectorProps) {
    return (
        <div className="model-selector" id="model-selector">
            <Dropdown
                items={AVAILABLE_MODELS.map((m) => ({ label: m.label, value: m.id }))}
                value={value}
                onChange={onChange}
                placeholder="Select Model"
            />
        </div>
    );
}
