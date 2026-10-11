import { ReactNode, useEffect, useRef } from "react";

interface ModalProps {
    isOpen: boolean;
    onClose: () => void;
    title?: string;
    children: ReactNode;
}

export default function Modal({ isOpen, onClose, title, children }: ModalProps) {
    const dialogRef = useRef<HTMLDialogElement>(null);

    useEffect(() => {
        const dialog = dialogRef.current;
        if (!dialog) return;
        if (isOpen) {
            dialog.showModal();
        } else {
            dialog.close();
        }
    }, [isOpen]);

    return (
        <dialog ref={dialogRef} className="modal" onClose={onClose}>
            <div className="modal-content">
                {title && (
                    <div className="modal-header">
                        <h2>{title}</h2>
                        <button className="modal-close" onClick={onClose} aria-label="Close">
                            ×
                        </button>
                    </div>
                )}
                <div className="modal-body">{children}</div>
            </div>
        </dialog>
    );
}
