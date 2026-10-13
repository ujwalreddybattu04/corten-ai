"use client";
import { useEffect } from "react";
import Link from "next/link";

export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset?: () => void }) {
    useEffect(() => {
        // Keep failures observable (browser console and monitoring); the digest links to server logs.
        console.error("[Corten] Page error", error?.digest ? `(digest ${error.digest})` : "", error);
    }, [error]);
    return <div className="account-settings" role="alert">
        <h1>This page could not load</h1>
        <p className="account-description">Please try again, or return to Search.</p>
        <button className="auth-submit" onClick={() => (reset ? reset() : window.location.reload())}>Try again</button>
        <p><Link href="/">Return to Search</Link></p>
    </div>;
}
