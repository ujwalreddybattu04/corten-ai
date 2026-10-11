"use client";

import { useState } from "react";

const CATEGORIES = ["All", "Technology", "Science", "Business", "Health", "Sports", "Entertainment"];

interface CategoryFilterProps {
    onSelect?: (category: string) => void;
}

export default function CategoryFilter({ onSelect }: CategoryFilterProps) {
    const [active, setActive] = useState("All");

    const handleSelect = (category: string) => {
        setActive(category);
        onSelect?.(category);
    };

    return (
        <div className="category-filter" id="category-filter">
            {CATEGORIES.map((category) => (
                <button
                    key={category}
                    className={`category-filter-btn ${active === category ? "active" : ""}`}
                    onClick={() => handleSelect(category)}
                >
                    {category}
                </button>
            ))}
        </div>
    );
}
