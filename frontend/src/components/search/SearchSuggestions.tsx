interface SearchSuggestionsProps {
    suggestions: string[];
    onSelect: (suggestion: string) => void;
    visible: boolean;
}

export default function SearchSuggestions({
    suggestions,
    onSelect,
    visible,
}: SearchSuggestionsProps) {
    if (!visible || suggestions.length === 0) return null;

    return (
        <div className="search-suggestions" id="search-suggestions">
            {suggestions.map((suggestion, index) => (
                <button
                    key={index}
                    className="search-suggestion-item"
                    onClick={() => onSelect(suggestion)}
                >
                    {suggestion}
                </button>
            ))}
        </div>
    );
}
