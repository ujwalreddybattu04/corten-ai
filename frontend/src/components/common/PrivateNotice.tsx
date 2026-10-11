"use client";

import React, { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, X } from "lucide-react";
import "@/styles/components/PrivateNotice.css";

interface PrivateNoticeProps {
    isVisible: boolean;
    onClose: () => void;
}

export default function PrivateNotice({ isVisible, onClose }: PrivateNoticeProps) {
    // Auto-dismiss after 5 seconds
    useEffect(() => {
        if (isVisible) {
            const timer = setTimeout(() => {
                onClose();
            }, 5000);
            return () => clearTimeout(timer);
        }
    }, [isVisible, onClose]);

    return (
        <AnimatePresence>
            {isVisible && (
                <motion.div
                    className="private-toast"
                    initial={{ opacity: 0, x: 50, scale: 0.9 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    exit={{ opacity: 0, x: 20, scale: 0.95 }}
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                >
                    <div className="private-toast-icon">
                        <ShieldCheck size={20} strokeWidth={2} />
                    </div>

                    <div className="private-toast-content">
                        <h3 className="private-toast-title">Private Session Active</h3>
                        <p className="private-toast-msg">History and threads will not be saved.</p>
                    </div>

                    <button className="private-toast-close" onClick={onClose} aria-label="Close">
                        <X size={14} />
                    </button>

                    {/* Progress bar for auto-dismiss */}
                    <motion.div
                        className="private-toast-progress"
                        initial={{ width: "100%" }}
                        animate={{ width: "0%" }}
                        transition={{ duration: 5, ease: "linear" }}
                    />
                </motion.div>
            )}
        </AnimatePresence>
    );
}
