interface CitationBadgeProps {
    index: number;
    onClick?: () => void;
}

export default function CitationBadge({ index, onClick }: CitationBadgeProps) {
    return (
        <sup
            className="citation-badge"
            onClick={onClick}
            role="button"
            tabIndex={0}
            aria-label={`Source ${index}`}
        >
            [{index}]
        </sup>
    );
}
