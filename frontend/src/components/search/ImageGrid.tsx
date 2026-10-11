interface ImageGridProps {
    images: { url: string; alt: string; sourceUrl: string }[];
}

export default function ImageGrid({ images }: ImageGridProps) {
    if (images.length === 0) return null;

    return (
        <div className="image-grid" id="image-grid">
            {images.map((image, index) => (
                <a
                    key={index}
                    href={image.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="image-grid-item"
                >
                    <img src={image.url} alt={image.alt} loading="lazy" />
                </a>
            ))}
        </div>
    );
}
