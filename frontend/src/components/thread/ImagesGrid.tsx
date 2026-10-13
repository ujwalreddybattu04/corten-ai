"use client";

import { useState, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import type { SearchImage } from "@/hooks/useSearch";
import { imageCandidates, imageUrl } from "@/lib/searchImages";

interface ImagesGridProps {
    images: SearchImage[];
    /** strip = horizontal scroll row (Answer tab), grid = full masonry grid (Images tab) */
    mode?: "strip" | "grid";
}

function RecoverableImage({ image, preview = true, className, lazy = false }: {
    image: SearchImage; preview?: boolean; className: string; lazy?: boolean;
}) {
    const [attempt, setAttempt] = useState(0);
    const candidates = imageCandidates(image, preview);
    if (attempt >= candidates.length) return <span className="image-unavailable" role="status">Image unavailable</span>;
    // Load search assets directly, without an arbitrary-URL image proxy.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={candidates[attempt]} alt={image.alt || "Search image"} className={className}
        loading={lazy ? "lazy" : "eager"} decoding="async" referrerPolicy="no-referrer"
        onError={() => setAttempt(value => value + 1)} />;
}

// ─── Lightbox ────────────────────────────────────────────────────────────────
function Lightbox({
    img, index, total, closing,
    onClose, onPrev, onNext,
}: {
    img: SearchImage;
    index: number;
    total: number;
    closing: boolean;
    onClose: () => void;
    onPrev: () => void;
    onNext: () => void;
}) {
    return (
        <div
            className={`lightbox-overlay${closing ? " lightbox-closing" : ""}`}
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-label="Image lightbox"
        >
            {/* Close */}
            <button className="lightbox-close" onClick={onClose} aria-label="Close" suppressHydrationWarning>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
            </button>

            {/* Navigation arrows */}
            {total > 1 && (
                <>
                    <button
                        className="lightbox-nav lightbox-prev"
                        onClick={e => { e.stopPropagation(); onPrev(); }}
                        aria-label="Previous image"
                        suppressHydrationWarning
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
                            fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="15 18 9 12 15 6" />
                        </svg>
                    </button>
                    <button
                        className="lightbox-nav lightbox-next"
                        onClick={e => { e.stopPropagation(); onNext(); }}
                        aria-label="Next image"
                        suppressHydrationWarning
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
                            fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="9 18 15 12 9 6" />
                        </svg>
                    </button>
                </>
            )}

            {/* Content */}
            <div
                className={`lightbox-content${closing ? " lightbox-content-closing" : ""}`}
                onClick={e => e.stopPropagation()}
            >
                <RecoverableImage key={`${img.url}|${img.thumbnailUrl || ""}`} image={img} preview={false} className="lightbox-img" />
                {(img.alt || img.sourceUrl) && (
                    <div className="lightbox-footer">
                        {img.alt && <p className="lightbox-caption">{img.alt}</p>}
                        {imageUrl(img.sourceUrl) && (
                            <a
                                href={imageUrl(img.sourceUrl)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="lightbox-source-link"
                                onClick={e => e.stopPropagation()}
                            >
                                View source ↗
                            </a>
                        )}
                    </div>
                )}
            </div>

            {/* Counter */}
            {total > 1 && (
                <div className="lightbox-counter">{index + 1} / {total}</div>
            )}
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function ImagesGrid({ images, mode = "grid" }: ImagesGridProps) {
    const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
    const [closing, setClosing] = useState(false);


    const allImages = (images || []).filter(img => img && imageCandidates(img).length);

    const displayImages = mode === "strip"
        ? allImages.slice(0, 6)
        : allImages;

    const openLightbox = useCallback((idx: number) => {
        setLightboxIndex(idx);
        setClosing(false);
    }, []);

    const closeLightbox = useCallback(() => {
        setClosing(true);
        setTimeout(() => {
            setClosing(false);
            setLightboxIndex(null);
        }, 180);
    }, []);

    const navigate = useCallback((dir: 1 | -1) => {
        setLightboxIndex(prev =>
            prev === null ? 0 : (prev + dir + allImages.length) % allImages.length
        );
    }, [allImages.length]);

    // Keyboard navigation
    useEffect(() => {
        if (lightboxIndex === null) return;
        const h = (e: KeyboardEvent) => {
            if (e.key === "Escape") closeLightbox();
            if (e.key === "ArrowLeft") navigate(-1);
            if (e.key === "ArrowRight") navigate(1);
        };
        window.addEventListener("keydown", h);
        return () => window.removeEventListener("keydown", h);
    }, [lightboxIndex, closeLightbox, navigate]);

    const lightboxImg = lightboxIndex !== null ? allImages[lightboxIndex] : null;
    if (allImages.length === 0) return mode === "grid"
        ? <div className="sp-images-loading" role="status">No displayable images for this answer.</div> : null;

    // ── STRIP MODE (Answer tab) ───────────────────────────────────────────────
    if (mode === "strip") {
        return (
            <>
                <div className="images-strip-section">
                    <div className="images-strip-label">Images</div>
                    <div className="images-strip">
                        {displayImages.map((img, i) => (
                            <button
                                key={i}
                                className="images-strip-item"
                                style={{ "--stagger-index": i } as React.CSSProperties}
                                onClick={() => openLightbox(i)}
                                aria-label={img.alt || "View image"}
                                suppressHydrationWarning
                            >
                                <RecoverableImage key={`${img.url}|${img.thumbnailUrl || ""}`} image={img}
                                    className="images-strip-img" lazy />
                                <div className="images-strip-overlay">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                        fill="none" stroke="currentColor" strokeWidth="2.5">
                                        <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                                    </svg>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {lightboxImg && typeof document !== "undefined" && createPortal(
                    <Lightbox
                        img={lightboxImg}
                        index={lightboxIndex!}
                        total={allImages.length}
                        closing={closing}
                        onClose={closeLightbox}
                        onPrev={() => navigate(-1)}
                        onNext={() => navigate(1)}
                    />,
                    document.body
                )}
            </>
        );
    }

    // ── GRID MODE (Images tab) ────────────────────────────────────────────────
    return (
        <>
            <div className="images-grid-full">
                {displayImages.map((img, i) => (
                    <button
                        key={i}
                        className="images-grid-item-new"
                        style={{ "--stagger-index": i } as React.CSSProperties}
                        onClick={() => openLightbox(i)}
                        aria-label={img.alt || "View image"}
                        suppressHydrationWarning
                    >
                        <RecoverableImage key={`${img.url}|${img.thumbnailUrl || ""}`} image={img}
                            className="images-grid-img-new" lazy />
                        <div className="images-grid-overlay-new">
                            {img.alt && (
                                <span className="images-grid-caption-new">{img.alt}</span>
                            )}
                        </div>
                    </button>
                ))}
            </div>

            {lightboxImg && typeof document !== "undefined" && createPortal(
                <Lightbox
                    img={lightboxImg}
                    index={lightboxIndex!}
                    total={allImages.length}
                    closing={closing}
                    onClose={closeLightbox}
                    onPrev={() => navigate(-1)}
                    onNext={() => navigate(1)}
                />,
                document.body
            )}
        </>
    );
}
