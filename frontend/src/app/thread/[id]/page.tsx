import { redirect } from "next/navigation";
export default async function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = await params;
    redirect(`/search?id=${encodeURIComponent(id)}`);
}
