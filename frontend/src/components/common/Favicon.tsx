"use client";

import React, { useState } from "react";
import "@/styles/components/Favicon.css";

interface FaviconProps {
    url: string;
    domain: string;
    size?: number;
}

export default function Favicon({ url, domain, size = 16 }: FaviconProps) {
    const [error, setError] = useState(false);

    // Clean domain for letter generation (e.g., "www.google.com" -> "G")
    const cleanDomain = domain.replace(/^www\./, "");
    const initial = cleanDomain.charAt(0).toUpperCase();

    // Deterministic color based on domain name
    const colors = [
        "linear-gradient(135deg, #6366f1 0%, #a855f7 100%)", // Indigo -> Purple
        "linear-gradient(135deg, #3b82f6 0%, #2dd4bf 100%)", // Blue -> Teal
        "linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)", // Amber -> Red
        "linear-gradient(135deg, #10b981 0%, #3b82f6 100%)", // Emerald -> Blue
        "linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%)", // Pink -> Violet
    ];

    // Simple hash function for consistent color selection
    const colorIndex = cleanDomain.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0) % colors.length;
    const bgGradient = colors[colorIndex];

    if (error || !url) {
        return (
            <div
                className="favicon-fallback"
                style={{
                    width: size,
                    height: size,
                    background: bgGradient,
                    fontSize: size * 0.65,
                }}
            >
                {initial}
            </div>
        );
    }

    return (
        <div className="favicon-container" style={{ width: size, height: size }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src={`https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${url}&size=64`}
                alt=""
                width={size}
                height={size}
                className="favicon-img"
                onError={() => setError(true)}
            />
        </div>
    );
}
