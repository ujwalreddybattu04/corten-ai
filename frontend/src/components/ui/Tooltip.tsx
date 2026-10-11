import { ReactNode, useState } from "react";

interface TooltipProps {
    content: string;
    children: ReactNode;
    position?: "top" | "bottom" | "left" | "right";
}

export default function Tooltip({ content, children, position = "top" }: TooltipProps) {
    const [visible, setVisible] = useState(false);

    return (
        <div
            className="tooltip-wrapper"
            onMouseEnter={() => setVisible(true)}
            onMouseLeave={() => setVisible(false)}
        >
            {children}
            {visible && <div className={`tooltip tooltip-${position}`}>{content}</div>}
        </div>
    );
}
