"use client";
import Link from "next/link";
export default function PageError({ retry }: { error: unknown; retry: () => void }) {
    return <div className="account-settings" role="alert">
        <h1>This page could not load</h1>
        <p className="account-description">Please try again, or return to Search.</p>
        <button className="auth-submit" onClick={retry}>Try again</button>
        <p><Link href="/">Return to Search</Link></p>
    </div>;
}
