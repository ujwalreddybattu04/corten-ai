"use client";

import { useState } from "react";
import { FOCUS_MODES } from "@/config/focusModes";

export default function FocusMode() {
    const [active, setActive] = useState("all");

    return (
        <div className="focus-mode" id="focus-mode-selector">
            {FOCUS_MODES.map((mode) => (
                <button
                    key={mode.value}
                    className={`focus-mode-btn ${active === mode.value ? "active" : ""}`}
                    onClick={() => setActive(mode.value)}
                    title={mode.description}
                >
                    <span className="focus-mode-icon">{mode.icon}</span>
                    <span className="focus-mode-label">{mode.label}</span>
                </button>
            ))}
        </div>
    );
}
