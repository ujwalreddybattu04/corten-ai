import Link from "next/link";

export default function NotFound() {
    return (
        <div className="not-found-page">
            <h1>404</h1>
            <p>The page you&apos;re looking for doesn&apos;t exist.</p>
            <Link href="/" className="btn-primary">
                Go Home
            </Link>
        </div>
    );
}
