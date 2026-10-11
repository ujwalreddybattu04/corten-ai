"use client";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";

export default function SettingsPage() {
    const { user, logout, sessionError, reloadSession } = useAuth();
    return <div className="account-settings">
        <h1>Account settings</h1>
        <p className="account-description">Manage your Corten session.</p>
        {sessionError && <div className="auth-error-banner" role="alert">{sessionError}<button onClick={() => void reloadSession()}>Retry</button></div>}
        <section className="account-panel">
            <h2>{user ? "Your account" : "Sign in to Corten"}</h2>
            {user ? <><dl><dt>Name</dt><dd>{user.name}</dd><dt>Email</dt><dd>{user.email}</dd><dt>Plan</dt><dd>{user.subscription_tier}</dd></dl>
                <button className="auth-submit" onClick={() => void logout()}>Sign out</button></> :
                <><p>Use your email and password to access your account.</p><Link className="auth-submit" href="/auth/login?next=%2Fsettings">Sign in</Link><p><Link href="/auth/signup?next=%2Fsettings">Create an account</Link></p></>}
        </section>
        <p className="account-description">Chat history, Spaces, and analyst projects are stored in this browser, separately for each account. Team synchronization is not yet available.</p>
    </div>;
}