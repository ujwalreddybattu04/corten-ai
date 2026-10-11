import { AuthProvider } from "@/contexts/AuthContext";

/**
 * Auth layout — wraps /auth/* pages with AuthProvider.
 * The auth pages use position:fixed to cover the sidebar from the root layout.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return <AuthProvider>{children}</AuthProvider>;
}
