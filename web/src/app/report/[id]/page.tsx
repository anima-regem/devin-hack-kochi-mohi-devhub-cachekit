import { ReportWorkspace } from "@/components/workspace";

export default async function Report({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportWorkspace key={id} id={id} />;
}
