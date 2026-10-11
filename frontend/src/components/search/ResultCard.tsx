interface ResultCardProps {
    title: string;
    snippet: string;
    url: string;
    domain: string;
    faviconUrl?: string;
}

export default function ResultCard({ title, snippet, url, domain, faviconUrl }: ResultCardProps) {
    return (
        <a href={url} target="_blank" rel="noopener noreferrer" className="result-card">
            <div className="result-card-header">
                {faviconUrl && <img src={faviconUrl} alt="" className="result-card-favicon" width={16} height={16} />}
                <span className="result-card-domain">{domain}</span>
            </div>
            <h3 className="result-card-title">{title}</h3>
            <p className="result-card-snippet">{snippet}</p>
        </a>
    );
}
