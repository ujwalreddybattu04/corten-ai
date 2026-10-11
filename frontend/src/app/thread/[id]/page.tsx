export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
    return (
        <div className="thread-page">
            <div className="thread-messages">
                {/* MessageBubble components — conversation history */}
            </div>
            <aside className="thread-sources-sidebar">
                {/* SourcesPanel — all sources from this thread */}
            </aside>
            <div className="thread-input-bar">
                {/* FollowUpInput — ask follow-up questions */}
            </div>
        </div>
    );
}
