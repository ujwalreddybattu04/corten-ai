interface TrendingCardProps {
    title: string;
    category: string;
    preview: string;
    imageUrl?: string;
    onClick: () => void;
}

export default function TrendingCard({ title, category, preview, imageUrl, onClick }: TrendingCardProps) {
    return (
        <button className="trending-card" onClick={onClick}>
            {imageUrl && <img src={imageUrl} alt={title} className="trending-card-image" />}
            <div className="trending-card-content">
                <span className="trending-card-category">{category}</span>
                <h3 className="trending-card-title">{title}</h3>
                <p className="trending-card-preview">{preview}</p>
            </div>
        </button>
    );
}
