// useFocusMode — hook for managing search focus mode
import { useState } from "react";

export type FocusModeValue = "all" | "academic" | "youtube" | "reddit" | "writing" | "math" | "social";

export function useFocusMode() {
    const [focusMode, setFocusMode] = useState<FocusModeValue>("all");

    return { focusMode, setFocusMode };
}
