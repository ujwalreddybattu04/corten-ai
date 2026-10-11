interface AvatarProps {
    src?: string;
    name: string;
    size?: number;
}

export default function Avatar({ src, name, size = 32 }: AvatarProps) {
    return (
        <div className="avatar" style={{ width: size, height: size }}>
            {src ? (
                <img src={src} alt={name} className="avatar-image" width={size} height={size} />
            ) : (
                <span className="avatar-fallback">{name[0]?.toUpperCase()}</span>
            )}
        </div>
    );
}
