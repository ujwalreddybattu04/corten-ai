"use client";
import { useRef, useState } from "react";
import { X, Loader2 } from "lucide-react";
import { useModalFocus } from "@/hooks/useModalFocus";
import type { Space, SpaceFields } from "@/lib/spacesApi";
import { SPACE_COLORS, SPACE_ICONS, SpaceIcon } from "./SpaceVisuals";

const INSTRUCTIONS_LIMIT = 8000;

export default function SpaceFormModal({ initial, onSubmit, onClose }: {
    initial?: Space;
    onSubmit: (fields: SpaceFields & { name: string }) => Promise<void>;
    onClose: () => void;
}) {
    const [name, setName] = useState(initial?.name ?? "");
    const [description, setDescription] = useState(initial?.description ?? "");
    const [instructions, setInstructions] = useState("");
    const [icon, setIcon] = useState(initial?.icon ?? "book");
    const [color, setColor] = useState(initial?.color ?? SPACE_COLORS[0]);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const dialogRef = useRef<HTMLDivElement>(null);
    useModalFocus(dialogRef, true, () => { if (!saving) onClose(); });

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!name.trim() || saving) return;
        setSaving(true);
        setError("");
        try {
            await onSubmit({ name: name.trim(), description: description.trim(), icon, color,
                ...(initial ? {} : { instructions: instructions.trim() }) });
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "The Space could not be saved. Please retry.");
            setSaving(false);
        }
    };

    return (
        <div className="sp-spaces-overlay" onMouseDown={event => { if (event.target === event.currentTarget && !saving) onClose(); }}>
            <div ref={dialogRef} className="sp-spaces-form-modal sx-form-modal" role="dialog" aria-modal="true"
                aria-labelledby="space-form-title">
                <div className="sp-spaces-form-header">
                    <h2 id="space-form-title">{initial ? "Space details" : "Create a Space"}</h2>
                    <button className="sp-spaces-form-close" aria-label="Close" onClick={onClose} disabled={saving}><X size={18} /></button>
                </div>
                <form onSubmit={submit} className="sp-spaces-form">
                    <div className="sp-spaces-form-preview">
                        <SpaceIcon icon={icon} color={color} size={24} box={48} />
                        <div className="sx-form-preview-text">
                            <span className="sp-spaces-form-preview-name">{name.trim() || "Untitled Space"}</span>
                            <span className="sx-muted">{description.trim() || "A shared home for research, files and answers"}</span>
                        </div>
                    </div>

                    <div className="sp-spaces-form-field">
                        <label htmlFor="space-name">Name</label>
                        <input id="space-name" className="sx-input" autoFocus required maxLength={100} value={name}
                            placeholder="e.g. Oncology market intelligence" onChange={event => setName(event.target.value)} />
                    </div>
                    <div className="sp-spaces-form-field">
                        <label htmlFor="space-description">Description <span className="sp-form-optional">optional</span></label>
                        <textarea id="space-description" className="sx-input" rows={2} maxLength={2000} value={description}
                            placeholder="What is this Space for?" onChange={event => setDescription(event.target.value)} />
                    </div>
                    {!initial && (
                        <div className="sp-spaces-form-field">
                            <label htmlFor="space-instructions">Instructions for answers <span className="sp-form-optional">optional</span></label>
                            <textarea id="space-instructions" className="sx-input" rows={3} maxLength={INSTRUCTIONS_LIMIT} value={instructions}
                                placeholder="e.g. Answer as a market analyst. Use tables for comparisons and cite regulatory sources."
                                onChange={event => setInstructions(event.target.value)} />
                            <span className="sx-hint">Applied to every question asked in this Space. You can add files and links next.</span>
                        </div>
                    )}
                    <fieldset className="sp-spaces-form-field sx-fieldset">
                        <legend>Icon</legend>
                        <div className="sp-spaces-icon-grid" role="radiogroup" aria-label="Icon">
                            {SPACE_ICONS.map(({ key, label, Icon }) => (
                                <button key={key} type="button" role="radio" aria-checked={icon === key} aria-label={label} title={label}
                                    className={`sp-spaces-icon-btn ${icon === key ? "active" : ""}`}
                                    style={icon === key ? { background: color + "20", color } : undefined}
                                    onClick={() => setIcon(key)}>
                                    <Icon size={20} />
                                </button>
                            ))}
                        </div>
                    </fieldset>
                    <fieldset className="sp-spaces-form-field sx-fieldset">
                        <legend>Color</legend>
                        <div className="sp-spaces-color-grid" role="radiogroup" aria-label="Color">
                            {SPACE_COLORS.map(option => (
                                <button key={option} type="button" role="radio" aria-checked={color === option} aria-label={option}
                                    className={`sp-spaces-color-btn ${color === option ? "active" : ""}`}
                                    style={{ background: option }} onClick={() => setColor(option)} />
                            ))}
                        </div>
                    </fieldset>
                    {error && <p className="sx-error" role="alert">{error}</p>}
                    <div className="sp-spaces-form-actions">
                        <button type="button" className="sp-spaces-form-cancel" onClick={onClose} disabled={saving}>Cancel</button>
                        <button type="submit" className="sp-spaces-form-submit" disabled={!name.trim() || saving}>
                            {saving && <Loader2 size={14} className="sx-spin" />}
                            {initial ? "Save changes" : "Create Space"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
