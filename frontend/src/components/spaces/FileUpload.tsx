"use client";

import { useRef } from "react";

interface FileUploadProps {
    onUpload: (files: FileList) => void;
    accept?: string;
}

export default function FileUpload({ onUpload, accept = "*" }: FileUploadProps) {
    const inputRef = useRef<HTMLInputElement>(null);

    return (
        <div className="file-upload" id="file-upload">
            <input
                ref={inputRef}
                type="file"
                multiple
                accept={accept}
                onChange={(e) => e.target.files && onUpload(e.target.files)}
                className="file-upload-input"
            />
            <button className="file-upload-btn" onClick={() => inputRef.current?.click()}>
                📎 Upload Files
            </button>
        </div>
    );
}
