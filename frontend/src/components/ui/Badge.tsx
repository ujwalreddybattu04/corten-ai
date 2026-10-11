import { ReactNode } from "react";

interface BadgeProps {
    variant?: "default" | "success" | "warning" | "error" | "info";
    children: ReactNode;
}

export default function Badge({ variant = "default", children }: BadgeProps) {
    return <span className={`badge badge-${variant}`}>{children}</span>;
}
