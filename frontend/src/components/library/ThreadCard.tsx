interface ThreadCardProps {
    id: string;
    title: string;
    preview: string;
    createdAt: string;
    messageCount: number;
}

export default function ThreadCard({ id, title, preview, createdAt, messageCount }: ThreadCardProps) {
    return (
        <a href={`/thread/${id}`} className="thread-card" id={`thread-card-${id}`}>
            <h3 className="thread-card-title">{title}</h3>
            <p className="thread-card-preview">{preview}</p>
            <div className="thread-card-meta">
                <span>{createdAt}</span>
                <span>{messageCount} messages</span>
            </div>
        </a>
    );
}
