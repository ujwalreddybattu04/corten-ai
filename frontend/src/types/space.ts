export interface Space {
    id: string;
    ownerId: string;
    name: string;
    description?: string;
    customInstructions?: string;
    members: SpaceMember[];
    files: SpaceFile[];
    createdAt: string;
    updatedAt: string;
}

export interface SpaceMember {
    userId: string;
    name: string;
    avatarUrl?: string;
    role: "owner" | "contributor" | "viewer";
}

export interface SpaceFile {
    id: string;
    name: string;
    size: number;
    type: string;
    uploadedAt: string;
}
