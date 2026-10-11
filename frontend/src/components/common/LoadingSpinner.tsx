export default function LoadingSpinner({ size = 24 }: { size?: number }) {
    return (
        <div className="loading-spinner" style={{ width: size, height: size }} role="status">
            <span className="sr-only">Loading...</span>
        </div>
    );
}
