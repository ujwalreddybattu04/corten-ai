export default function AnswerSkeleton() {
    return (
        <div className="answer-skeleton">
            {/* Sources skeleton */}
            <div className="skeleton-sources">
                {[1, 2, 3, 4].map(i => (
                    <div key={i} className="skeleton-source-card">
                        <div className="skeleton-line skeleton-favicon" />
                        <div className="skeleton-line skeleton-domain" />
                        <div className="skeleton-line skeleton-title" />
                        <div className="skeleton-line skeleton-snippet" />
                    </div>
                ))}
            </div>

            {/* Images skeleton */}
            <div className="skeleton-images">
                {[1, 2, 3, 4].map(i => (
                    <div key={i} className="skeleton-image" />
                ))}
            </div>

            {/* Answer skeleton */}
            <div className="skeleton-answer">
                <div className="skeleton-line skeleton-w-90" />
                <div className="skeleton-line skeleton-w-75" />
                <div className="skeleton-line skeleton-w-85" />
                <div className="skeleton-line skeleton-w-60" />
                <div className="skeleton-line skeleton-w-80" />
                <div className="skeleton-line skeleton-w-70" />
                <div className="skeleton-line skeleton-spacer" />
                <div className="skeleton-line skeleton-w-90" />
                <div className="skeleton-line skeleton-w-65" />
                <div className="skeleton-line skeleton-w-80" />
            </div>
        </div>
    );
}
