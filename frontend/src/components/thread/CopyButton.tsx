"use client";

import { useState } from "react";

interface CopyButtonProps {
    text: string;
}

export default function CopyButton({ text }: CopyButtonProps) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <button className="copy-btn" onClick={handleCopy} title="Copy to clipboard" id="copy-btn">
            {copied ? "✓ Copied" : "📋 Copy"}
        </button>
    );
}
