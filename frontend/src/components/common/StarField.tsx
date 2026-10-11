"use client";

import { useEffect, useRef } from "react";

interface Star {
    x: number;
    y: number;
    size: number;
    opacity: number;
    speed: number;
    color: string;
}

export default function StarField() {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const starsRef = useRef<Star[]>([]);
    const animationRef = useRef<number>(0);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const resize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };

        const createStars = () => {
            const starCount = Math.floor((canvas.width * canvas.height) / 8000);
            starsRef.current = [];

            for (let i = 0; i < starCount; i++) {
                const isBright = Math.random() < 0.2;
                starsRef.current.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height,
                    size: Math.random() * 1.8 + 0.3,
                    opacity: Math.random() * 0.6 + 0.1,
                    speed: Math.random() * 0.15 + 0.02,
                    color: isBright
                        ? `rgba(255, 255, 255, `
                        : `rgba(200, 200, 220, `,
                });
            }
        };

        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            starsRef.current.forEach((star) => {
                // Subtle twinkling
                const twinkle = Math.sin(Date.now() * 0.001 * star.speed + star.x) * 0.3 + 0.7;
                const finalOpacity = star.opacity * twinkle;

                ctx.beginPath();
                ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
                ctx.fillStyle = star.color + finalOpacity + ")";
                ctx.fill();

                // Very slow drift
                star.y -= star.speed * 0.3;
                star.x += Math.sin(Date.now() * 0.0005 + star.y) * 0.05;

                // Wrap around
                if (star.y < -5) {
                    star.y = canvas.height + 5;
                    star.x = Math.random() * canvas.width;
                }
            });

            animationRef.current = requestAnimationFrame(animate);
        };

        resize();
        createStars();
        animate();

        window.addEventListener("resize", () => {
            resize();
            createStars();
        });

        return () => {
            cancelAnimationFrame(animationRef.current);
            window.removeEventListener("resize", resize);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="starfield-canvas"
            id="starfield"
            aria-hidden="true"
        />
    );
}
