
/**
 * Auth pages use the global, server-verified AuthProvider.
 * The auth pages use position:fixed to cover the sidebar from the root layout.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
