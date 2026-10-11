"use client";

import { useState } from "react";

interface ShareButtonProps {
    threadId: string;
}

export default function ShareButton({ threadId }: ShareButtonProps) {
    const [shared, setShared] = useState(false);

    const handleShare = async () => {
        const url = `${window.location.origin}/thread/${threadId}`;
        await navigator.clipboard.writeText(url);
        setShared(true);
        setTimeout(() => setShared(false), 2000);
    };

    return (
        <button className="share-btn" onClick={handleShare} title="Share thread" id="share-btn">
            {shared ? "✓ Link Copied" : "🔗 Share"}
        </button>
    );
}
