import { HeatmapWorkspace } from "@/components/workspace";

export default async function Heatmap({ params }: { params: Promise<{ id: string; route: string }> }) {
  const { id, route } = await params;
  return <HeatmapWorkspace key={`${id}:${route}`} id={id} route={route} />;
}
