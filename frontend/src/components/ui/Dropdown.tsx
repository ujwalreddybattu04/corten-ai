import { ReactNode, useState, useRef, useEffect } from "react";

interface DropdownItem {
    label: string;
    value: string;
    icon?: ReactNode;
}

interface DropdownProps {
    items: DropdownItem[];
    value?: string;
    onChange: (value: string) => void;
    placeholder?: string;
}

export default function Dropdown({ items, value, onChange, placeholder = "Select..." }: DropdownProps) {
    const [isOpen, setIsOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    const selected = items.find((item) => item.value === value);

    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    return (
        <div className="dropdown" ref={ref}>
            <button className="dropdown-trigger" onClick={() => setIsOpen(!isOpen)}>
                {selected ? selected.label : placeholder}
            </button>
            {isOpen && (
                <div className="dropdown-menu">
                    {items.map((item) => (
                        <button
                            key={item.value}
                            className={`dropdown-item ${item.value === value ? "active" : ""}`}
                            onClick={() => {
                                onChange(item.value);
                                setIsOpen(false);
                            }}
                        >
                            {item.icon && <span className="dropdown-item-icon">{item.icon}</span>}
                            {item.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
