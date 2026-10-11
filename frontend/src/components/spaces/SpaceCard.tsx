interface SpaceCardProps {
    id: string;
    name: string;
    description?: string;
    memberCount: number;
    threadCount: number;
    lastActive?: string;
}

export default function SpaceCard({ id, name, description, memberCount, threadCount, lastActive }: SpaceCardProps) {
    return (
        <a href={`/spaces/${id}`} className="space-card" id={`space-${id}`}>
            <h3 className="space-card-name">{name}</h3>
            {description && <p className="space-card-description">{description}</p>}
            <div className="space-card-meta">
                <span>{memberCount} members</span>
                <span>{threadCount} threads</span>
                {lastActive && <span>Active {lastActive}</span>}
            </div>
        </a>
    );
}
