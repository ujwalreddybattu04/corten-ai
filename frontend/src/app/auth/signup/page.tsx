"use client";

import React, { useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { ApiRequestError } from "@/lib/api";
import { BRAND_NAME } from "@/config/constants";

// ── Icons ─────────────────────────────────────────────────────────────────────

function GoogleIcon() {
    return (
        <svg className="btn-oauth-icon" viewBox="0 0 18 18" fill="none">
            <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
            <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
        </svg>
    );
}

function AppleIcon() {
    return (
        <svg className="btn-oauth-icon" viewBox="0 0 18 18" fill="currentColor">
            <path d="M14.17 9.55c-.02-2.13 1.74-3.16 1.82-3.21-1-1.45-2.55-1.65-3.1-1.67-1.32-.13-2.58.79-3.25.79-.68 0-1.72-.77-2.83-.75-1.46.02-2.8.85-3.55 2.14-1.52 2.63-.4 6.53 1.09 8.67.72 1.05 1.58 2.22 2.7 2.18 1.09-.04 1.5-.7 2.82-.7 1.32 0 1.69.7 2.84.68 1.17-.02 1.91-1.07 2.63-2.12.83-1.21 1.18-2.38 1.2-2.44-.03-.01-2.3-.89-2.37-3.57zm-2.22-6.55c.6-.73 1.01-1.73.9-2.74-.87.04-1.92.58-2.54 1.3-.55.63-.98 1.65-.86 2.62.97.08 1.94-.49 2.5-1.18z"/>
        </svg>
    );
}

function EyeIcon({ visible }: { visible: boolean }) {
    return visible ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>
            <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
            <line x1="1" y1="1" x2="23" y2="23"/>
        </svg>
    ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
        </svg>
    );
}

function AlertIcon() {
    return (
        <svg className="auth-error-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <circle cx="8" cy="8" r="6.5"/>
            <line x1="8" y1="5" x2="8" y2="8.5"/>
            <circle cx="8" cy="11" r="0.6" fill="currentColor" stroke="none"/>
        </svg>
    );
}

function UserIcon() {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
        </svg>
    );
}

function EmailIcon() {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="4" width="20" height="16" rx="2"/>
            <path d="M2 7l10 7 10-7"/>
        </svg>
    );
}

function LockIcon() {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2"/>
            <path d="M7 11V7a5 5 0 0110 0v4"/>
        </svg>
    );
}

function BrandLogo() {
    return (
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none">
            <path d="M3 8L7 4L13 8L7 12L3 8Z" fill="rgba(255,255,255,0.85)"/>
        </svg>
    );
}

// ── Password strength ─────────────────────────────────────────────────────────

function getPasswordStrength(pw: string): { score: number; label: string } {
    if (!pw) return { score: 0, label: "" };
    let score = 0;
    if (pw.length >= 8) score++;
    if (pw.length >= 12) score++;
    if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    const capped = Math.min(score, 4);
    return { score: capped, label: ["", "Weak", "Fair", "Good", "Strong"][capped] };
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function SignupPage() {
    const router = useRouter();
    const { register } = useAuth();

    const [name, setName]         = useState("");
    const [email, setEmail]       = useState("");
    const [password, setPassword] = useState("");
    const [showPw, setShowPw]     = useState(false);
    const [loading, setLoading]   = useState(false);
    const [globalError, setGlobalError] = useState("");
    const [fieldErrors, setFieldErrors] = useState<{
        name?: string; email?: string; password?: string;
    }>({});
    const [shakeField, setShakeField] = useState<string | null>(null);
    const [touched, setTouched] = useState({ name: false, email: false, password: false });

    const nameRef     = useRef<HTMLInputElement>(null);
    const emailRef    = useRef<HTMLInputElement>(null);
    const passwordRef = useRef<HTMLInputElement>(null);

    const pwStrength = getPasswordStrength(password);

    const validateName = useCallback((v: string) =>
        !v.trim() ? "Name is required" : v.trim().length < 2 ? "Name must be at least 2 characters" : "", []);
    const validateEmail = useCallback((v: string) =>
        !v.trim() ? "Email is required" : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? "Enter a valid email address" : "", []);
    const validatePassword = useCallback((v: string) =>
        !v ? "Password is required" : v.length < 8 ? "Password must be at least 8 characters" : "", []);

    const handleBlur = (field: "name" | "email" | "password") => {
        setTouched(t => ({ ...t, [field]: true }));
        const validators = { name: validateName, email: validateEmail, password: validatePassword };
        const values = { name, email, password };
        setFieldErrors(e => ({ ...e, [field]: validators[field](values[field]) }));
    };

    const triggerShake = (field: string) => {
        setShakeField(field);
        setTimeout(() => setShakeField(null), 400);
    };

    const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
        e.preventDefault();
        setGlobalError("");

        const nameErr     = validateName(name);
        const emailErr    = validateEmail(email);
        const passwordErr = validatePassword(password);

        setFieldErrors({ name: nameErr, email: emailErr, password: passwordErr });
        setTouched({ name: true, email: true, password: true });

        if (nameErr)     { triggerShake("name");     nameRef.current?.focus();     return; }
        if (emailErr)    { triggerShake("email");    emailRef.current?.focus();    return; }
        if (passwordErr) { triggerShake("password"); passwordRef.current?.focus(); return; }

        setLoading(true);
        try {
            await register(name.trim(), email, password);
            router.push("/");
        } catch (err) {
            if (err instanceof ApiRequestError) {
                if (err.status === 409) {
                    setFieldErrors(f => ({ ...f, email: "An account with this email already exists." }));
                    setTouched(t => ({ ...t, email: true }));
                    triggerShake("email");
                    emailRef.current?.focus();
                } else {
                    setGlobalError(err.message || "Something went wrong. Please try again.");
                }
            } else {
                setGlobalError("Unable to connect. Please check your connection and try again.");
            }
        } finally {
            setLoading(false);
        }
    };

    const inputClass = (field: "name" | "email" | "password", hasIcon = false) =>
        ["auth-input", hasIcon && "has-icon",
            touched[field] && fieldErrors[field] && "is-error",
            shakeField === field && "do-shake"]
            .filter(Boolean).join(" ");

    return (
        <div className="auth-shell">
            <div className="auth-card" role="main">
                <div className="auth-card-content">
                    <div className="auth-brand">
                        <div className="auth-brand-logo"><BrandLogo /></div>
                        <span className="auth-brand-name">{BRAND_NAME}</span>
                    </div>

                    <h1 className="auth-heading">Create Account</h1>
                    <p className="auth-subheading">Join {BRAND_NAME} and start searching smarter</p>

                    <div className="auth-oauth-stack">
                        <button type="button" className="btn-oauth" disabled={loading}
                            onClick={() => setGlobalError("OAuth coming soon — use email for now")}>
                            <GoogleIcon />
                            Google
                        </button>
                        <button type="button" className="btn-oauth" disabled={loading}
                            onClick={() => setGlobalError("OAuth coming soon — use email for now")}>
                            <AppleIcon />
                            Apple
                        </button>
                    </div>

                    <div className="auth-divider" aria-hidden="true">
                        <div className="auth-divider-line" />
                        <span className="auth-divider-text">or continue with email</span>
                        <div className="auth-divider-line" />
                    </div>

                    {globalError && (
                        <div className="auth-error-banner" role="alert">
                            <AlertIcon />
                            <span>{globalError}</span>
                        </div>
                    )}

                    <form className="auth-form" onSubmit={handleSubmit} noValidate>
                        {/* Full name */}
                        <div className="auth-field">
                            <label className="auth-label" htmlFor="signup-name">Full name</label>
                            <div className="auth-input-wrapper">
                                <span className="auth-input-icon"><UserIcon /></span>
                                <input
                                    ref={nameRef}
                                    id="signup-name"
                                    type="text"
                                    className={inputClass("name")}
                                    placeholder="Full Name"
                                    value={name}
                                    onChange={e => {
                                        setName(e.target.value);
                                        if (touched.name) setFieldErrors(f => ({ ...f, name: validateName(e.target.value) }));
                                    }}
                                    onBlur={() => handleBlur("name")}
                                    autoComplete="name"
                                    autoFocus
                                    disabled={loading}
                                />
                            </div>
                            {touched.name && fieldErrors.name && (
                                <span className="auth-field-error" role="alert">
                                    <AlertIcon />{fieldErrors.name}
                                </span>
                            )}
                        </div>

                        {/* Email */}
                        <div className="auth-field">
                            <label className="auth-label" htmlFor="signup-email">Email</label>
                            <div className="auth-input-wrapper">
                                <span className="auth-input-icon"><EmailIcon /></span>
                                <input
                                    ref={emailRef}
                                    id="signup-email"
                                    type="email"
                                    className={inputClass("email")}
                                    placeholder="Email ID"
                                    value={email}
                                    onChange={e => {
                                        setEmail(e.target.value);
                                        if (touched.email) setFieldErrors(f => ({ ...f, email: validateEmail(e.target.value) }));
                                    }}
                                    onBlur={() => handleBlur("email")}
                                    autoComplete="email"
                                    disabled={loading}
                                />
                            </div>
                            {touched.email && fieldErrors.email && (
                                <span className="auth-field-error" role="alert">
                                    <AlertIcon />{fieldErrors.email}
                                </span>
                            )}
                        </div>

                        {/* Password */}
                        <div className="auth-field">
                            <label className="auth-label" htmlFor="signup-password">Password</label>
                            <div className="auth-input-wrapper">
                                <span className="auth-input-icon"><LockIcon /></span>
                                <input
                                    ref={passwordRef}
                                    id="signup-password"
                                    type={showPw ? "text" : "password"}
                                    className={inputClass("password", true)}
                                    placeholder="Password"
                                    value={password}
                                    onChange={e => {
                                        setPassword(e.target.value);
                                        if (touched.password) setFieldErrors(f => ({ ...f, password: validatePassword(e.target.value) }));
                                    }}
                                    onBlur={() => handleBlur("password")}
                                    autoComplete="new-password"
                                    disabled={loading}
                                />
                                <button type="button" className="auth-pw-toggle"
                                    onClick={() => setShowPw(v => !v)}
                                    aria-label={showPw ? "Hide password" : "Show password"}
                                    tabIndex={-1}>
                                    <EyeIcon visible={showPw} />
                                </button>
                            </div>

                            {password.length > 0 && (
                                <div className="auth-pw-strength">
                                    <div className="auth-pw-strength-bar">
                                        <div className="auth-pw-strength-fill" data-strength={pwStrength.score} />
                                    </div>
                                    {pwStrength.label && (
                                        <p className="auth-pw-strength-label">{pwStrength.label}</p>
                                    )}
                                </div>
                            )}

                            {touched.password && fieldErrors.password && (
                                <span className="auth-field-error" role="alert">
                                    <AlertIcon />{fieldErrors.password}
                                </span>
                            )}
                        </div>

                        <button type="submit" className="auth-submit" disabled={loading}>
                            {loading ? (
                                <>
                                    <span className="auth-spinner" aria-hidden="true" />
                                    Creating account&hellip;
                                </>
                            ) : "Create Account"}
                        </button>
                    </form>

                    <p className="auth-switch">
                        Already have an account?
                        <Link href="/auth/login">Sign in</Link>
                    </p>

                    <p className="auth-terms">
                        By creating an account, you agree to our{" "}
                        <a href="/terms">Terms of Service</a> and{" "}
                        <a href="/privacy">Privacy Policy</a>.
                    </p>
                </div>
            </div>
        </div>
    );
}
