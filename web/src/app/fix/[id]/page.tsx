import { FixWorkspace } from "@/components/workspace";

export default async function Fix({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FixWorkspace key={id} id={id} />;
}
