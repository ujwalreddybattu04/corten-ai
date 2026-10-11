interface Member {
    id: string;
    name: string;
    avatarUrl?: string;
    role: "owner" | "contributor" | "viewer";
}

interface MemberListProps {
    members: Member[];
}

export default function MemberList({ members }: MemberListProps) {
    return (
        <div className="member-list" id="member-list">
            <h3 className="member-list-title">Members ({members.length})</h3>
            <div className="member-list-items">
                {members.map((member) => (
                    <div key={member.id} className="member-item">
                        <div className="member-avatar">
                            {member.avatarUrl ? (
                                <img src={member.avatarUrl} alt={member.name} width={32} height={32} />
                            ) : (
                                <span>{member.name[0]}</span>
                            )}
                        </div>
                        <span className="member-name">{member.name}</span>
                        <span className={`member-role member-role-${member.role}`}>{member.role}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
