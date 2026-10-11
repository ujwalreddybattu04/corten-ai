interface CollectionCardProps {
    id: string;
    name: string;
    threadCount: number;
    updatedAt: string;
}

export default function CollectionCard({ id, name, threadCount, updatedAt }: CollectionCardProps) {
    return (
        <div className="collection-card" id={`collection-${id}`}>
            <h3 className="collection-card-name">{name}</h3>
            <div className="collection-card-meta">
                <span>{threadCount} threads</span>
                <span>Updated {updatedAt}</span>
            </div>
        </div>
    );
}
