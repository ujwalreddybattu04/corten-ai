"use client";
import { useEffect, useState } from "react";
import { getCloudSyncStatus, getCloudSyncError, refreshCloudSync } from "@/lib/cloudSync";
import { useAuth } from "@/contexts/AuthContext";

export default function CloudSyncStatus() {
    const { user, reloadSession } = useAuth();
    const [status, setStatus] = useState(getCloudSyncStatus);
    const [error, setError] = useState(getCloudSyncError);
    useEffect(() => {
        const update = () => { setStatus(getCloudSyncStatus()); setError(getCloudSyncError()); };
        window.addEventListener("corten_sync_status", update);
        return () => window.removeEventListener("corten_sync_status", update);
    }, []);
    if (!user) return null;
    const storageBlocked = error.startsWith("Device storage is unavailable.");
    const text = storageBlocked ? error : { guest: "Saved on this device", loading: "Loading your saved work…", saved: "Saved to your account", pending: "Saving changes…", offline: "Saved on this device. Cloud sync unavailable.", conflict: "Conflicting edits kept as separate copies." }[status];
    return <div role="status" className="account-description" style={{ margin: "12px 0", fontSize: 12 }}>
        {text} {!storageBlocked && error} {(status === "offline" || status === "conflict") && <button onClick={() => void (storageBlocked ? reloadSession() : refreshCloudSync())} style={{ marginLeft: 8 }}>Retry sync</button>}
    </div>;
}
