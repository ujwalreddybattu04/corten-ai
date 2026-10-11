import { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
    label?: string;
    error?: string;
}

export default function Input({ label, error, id, className = "", ...props }: InputProps) {
    return (
        <div className={`input-group ${error ? "input-error" : ""} ${className}`}>
            {label && <label htmlFor={id}>{label}</label>}
            <input id={id} {...props} />
            {error && <span className="input-error-message">{error}</span>}
        </div>
    );
}
