import { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    isLoading?: boolean;
    children: ReactNode;
}

export default function Button({
    variant = "primary",
    size = "md",
    isLoading = false,
    children,
    className = "",
    disabled,
    ...props
}: ButtonProps) {
    return (
        <button
            className={`btn btn-${variant} btn-${size} ${isLoading ? "btn-loading" : ""} ${className}`}
            disabled={disabled || isLoading}
            {...props}
        >
            {isLoading ? <span className="spinner" /> : children}
        </button>
    );
}
