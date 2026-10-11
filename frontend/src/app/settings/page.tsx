export default function SettingsPage() {
    return (
        <div className="settings-page">
            <h1>Settings</h1>

            <section className="settings-section">
                <h2>AI Model</h2>
                {/* ModelSelector — default model preference */}
            </section>

            <section className="settings-section">
                <h2>Language</h2>
                {/* Language selector */}
            </section>

            <section className="settings-section">
                <h2>Account</h2>
                {/* Profile info, email, subscription */}
            </section>

            <section className="settings-section">
                <h2>API Keys</h2>
                {/* Custom API key inputs */}
            </section>
        </div>
    );
}
