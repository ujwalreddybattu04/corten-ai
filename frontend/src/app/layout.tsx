import type { Metadata } from "next";
import "@/styles/variables.css";
import "@/styles/globals.css";
import "@/styles/typography.css";
import "@/styles/animations.css";
import "@/styles/sidebar.css";
import "@/styles/searchbar.css";
import "@/styles/home.css";
import "@/styles/thread.css";
import "@/styles/share.css";
import "@/styles/components/PrivateToggle.css";
import "@/styles/code-runner.css";
import "@/styles/html-preview.css";
import "@/styles/auth.css";
import "@/styles/discover.css";
import "@/styles/history.css";
import "@/styles/spaces.css";
import "@/styles/report.css";
import { Suspense } from "react";
import { Sidebar } from "@/components/layout";
import { SITE_TITLE, SITE_DESCRIPTION, SITE_URL } from "@/config/constants";
import { AuthProvider } from "@/contexts/AuthContext";

export const metadata: Metadata = {
    metadataBase: new URL(SITE_URL),
    title: `${SITE_TITLE} — AI-Powered Answer Engine`,
    description: SITE_DESCRIPTION,
    openGraph: {
        title: SITE_TITLE,
        description: "AI-Powered Answer Engine",
        url: "/",
        siteName: SITE_TITLE,
        type: "website",
    },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en" data-theme="dark" suppressHydrationWarning>
            <head>
                <link rel="icon" href="/favicon.ico" />
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
                <link
                    href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400;1,500&family=IBM+Plex+Mono:wght@400;500&display=swap"
                    rel="stylesheet"
                />
            </head>
            <body suppressHydrationWarning>
                <AuthProvider>
                <div className="app-shell">
                    <Suspense fallback={<div style={{ width: "240px", backgroundColor: "var(--sidebar-bg)" }} />}>
                        <Sidebar />
                    </Suspense>
                    <main className="main-content">{children}</main>
                </div>
                </AuthProvider>
            </body>
        </html>
    );
}
