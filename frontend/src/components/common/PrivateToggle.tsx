"use client";

import { useState, useEffect } from "react";
import PrivateNotice from "./PrivateNotice";
import "@/styles/components/PrivateToggle.css"; // We will create this

export default function PrivateToggle() {
    const [isPrivateMode, setIsPrivateMode] = useState(false);
    const [showNotice, setShowNotice] = useState(false);

    useEffect(() => {
        // Hydrate from session storage on mount
        const stored = sessionStorage.getItem("corten_private_mode") === "true";
        setIsPrivateMode(stored);

        // Listen for external changes (optional, but good for robust state)
        const handleStorageChange = () => {
            setIsPrivateMode(sessionStorage.getItem("corten_private_mode") === "true");
        };
        window.addEventListener("corten_private_mode_toggle", handleStorageChange);
        return () => window.removeEventListener("corten_private_mode_toggle", handleStorageChange);
    }, []);

    const togglePrivate = () => {
        const newState = !isPrivateMode;
        setIsPrivateMode(newState);
        sessionStorage.setItem("corten_private_mode", String(newState));
        window.dispatchEvent(new Event("corten_private_mode_toggle"));

        // Show the professional notice when turning ON
        if (newState === true) {
            setShowNotice(true);
        }
    };

    return (
        <>
            <button
                className={`global-private-toggle ${isPrivateMode ? 'active' : ''}`}
                onClick={togglePrivate}
                aria-label="Toggle Private Mode"
                title="Private Mode: Zero Tracking"
            >
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0" />
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 5v2" />
                    <path d="M19.071 7.071l-1.414 1.414" />
                    <path d="M4.929 7.071l1.414 1.414" />
                    <path d="M5 12H3" />
                    <path d="M21 12h-2" />
                </svg>
                <span className="toggle-label">Private</span>
            </button>

            <PrivateNotice
                isVisible={showNotice}
                onClose={() => setShowNotice(false)}
            />
        </>
    );
}
