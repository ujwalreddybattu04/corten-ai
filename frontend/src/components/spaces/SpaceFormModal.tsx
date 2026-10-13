"use client";
import { useEffect, useRef, useState } from "react";
import { X, Loader2 } from "lucide-react";
import { useModalFocus } from "@/hooks/useModalFocus";
import type { Space, SpaceFields } from "@/lib/spacesApi";
import { DEFAULT_SPACE_ICON, SPACE_EMOJI, SpaceIcon } from "./SpaceVisuals";

const INSTRUCTIONS_LIMIT = 8000;

export default function SpaceFormModal({ initial, onSubmit, onClose }: {
    initial?: Space;
    onSubmit: (fields: SpaceFields & { name: string }) => Promise<void>;
    onClose: () => void;
}) {
    const [name, setName] = useState(initial?.name ?? "");
    const [description, setDescription] = useState(initial?.description ?? "");
    const [instructions, setInstructions] = useState("");
    const [icon, setIcon] = useState(initial?.icon ?? DEFAULT_SPACE_ICON);
    const [picking, setPicking] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const dialogRef = useRef<HTMLDivElement>(null);
    const nameRef = useRef<HTMLInputElement>(null);
    const pickerRef = useRef<HTMLDivElement>(null);
    // Escape closes the icon picker first, then the dialog.
    useModalFocus(dialogRef, true, () => { if (picking) setPicking(false); else if (!saving) onClose(); });
    useEffect(() => {
        const frame = requestAnimationFrame(() => nameRef.current?.focus());
        return () => cancelAnimationFrame(frame);
    }, []);
    useEffect(() => {
        if (!picking) return;
        const close = (event: MouseEvent) => { if (!pickerRef.current?.contains(event.target as Node)) setPicking(false); };
        document.addEventListener("mousedown", close);
        return () => document.removeEventListener("mousedown", close);
    }, [picking]);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!name.trim() || saving) return;
        setSaving(true);
        setError("");
        try {
            await onSubmit({ name: name.trim(), description: description.trim(), icon,
                ...(initial ? {} : { instructions: instructions.trim() }) });
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "The Space could not be saved. Please retry.");
            setSaving(false);
        }
    };

    return (
        <div className="sp-spaces-overlay" onMouseDown={event => { if (event.target === event.currentTarget && !saving) onClose(); }}>
            <div ref={dialogRef} className="sv-dialog" role="dialog" aria-modal="true" aria-labelledby="space-form-title">
                <div className="sv-dialog-head">
                    <h2 id="space-form-title">{initial ? "Edit Space" : "Create a Space"}</h2>
                    <button className="sx-icon-btn" aria-label="Close" onClick={onClose} disabled={saving}><X size={17} /></button>
                </div>
                <form onSubmit={submit} className="sv-form">
                    <div className="sv-name-row">
                        <div className="sv-emoji-anchor" ref={pickerRef}>
                            <button type="button" className="sv-emoji-btn" aria-label="Choose an icon" aria-haspopup="listbox"
                                aria-expanded={picking} onClick={() => setPicking(!picking)}>
                                <SpaceIcon icon={icon} size={46} />
                            </button>
                            {picking && (
                                <div className="sv-emoji-pop" role="listbox" aria-label="Icon">
                                    {SPACE_EMOJI.map(option => (
                                        <button key={option} type="button" role="option" aria-selected={icon === option}
                                            className={`sv-emoji-option ${icon === option ? "active" : ""}`}
                                            onClick={() => { setIcon(option); setPicking(false); nameRef.current?.focus(); }}>{option}</button>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div className="sv-field sv-field--grow">
                            <label htmlFor="space-name">Name</label>
                            <input ref={nameRef} id="space-name" className="sx-input sv-name-input" required maxLength={100} value={name}
                                placeholder="e.g. EU oncology launch" onChange={event => setName(event.target.value)} />
                        </div>
                    </div>
                    <div className="sv-field">
                        <label htmlFor="space-description">Description <span className="sv-optional">Optional</span></label>
                        <textarea id="space-description" className="sx-input" rows={2} maxLength={2000} value={description}
                            placeholder="What is this Space for?" onChange={event => setDescription(event.target.value)} />
                    </div>
                    {!initial && (
                        <div className="sv-field">
                            <label htmlFor="space-instructions">Instructions <span className="sv-optional">Optional</span></label>
                            <textarea id="space-instructions" className="sx-input" rows={4} maxLength={INSTRUCTIONS_LIMIT} value={instructions}
                                placeholder="How should answers in this Space be written? For example: answer as a market access analyst, use tables for comparisons, cite regulators first."
                                onChange={event => setInstructions(event.target.value)} />
                            <span className="sv-hint">Applied to every answer in this Space. Add files, links and people after creating it.</span>
                        </div>
                    )}
                    {error && <p className="sx-error" role="alert">{error}</p>}
                    <div className="sv-dialog-foot">
                        <button type="button" className="sx-btn sx-btn--ghost" onClick={onClose} disabled={saving}>Cancel</button>
                        <button type="submit" className="sx-btn sx-btn--primary" disabled={!name.trim() || saving}>
                            {saving && <Loader2 size={14} className="sx-spin" />}
                            {initial ? "Save" : "Create Space"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
