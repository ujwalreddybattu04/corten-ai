"use client";
import { Suspense } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

export default function AppFrame({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    if (pathname.startsWith("/auth/")) return <>{children}</>;
    return <div className="app-shell">
        <Suspense fallback={<div style={{ width: "240px", backgroundColor: "var(--sidebar-bg)" }} />}>
            <Sidebar />
        </Suspense>
        <main className="main-content">{children}</main>
    </div>;
}
