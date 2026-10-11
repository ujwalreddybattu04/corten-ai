interface SpaceHeaderProps {
    name: string;
    description?: string;
    customInstructions?: string;
}

export default function SpaceHeader({ name, description, customInstructions }: SpaceHeaderProps) {
    return (
        <div className="space-header">
            <h1 className="space-header-name">{name}</h1>
            {description && <p className="space-header-description">{description}</p>}
            {customInstructions && (
                <div className="space-header-instructions">
                    <h3>Custom Instructions</h3>
                    <p>{customInstructions}</p>
                </div>
            )}
        </div>
    );
}
