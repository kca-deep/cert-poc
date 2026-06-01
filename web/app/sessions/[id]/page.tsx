import { SessionView } from "@/components/dashboard/SessionView";

// Next 16: route params are async — must be awaited.
export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SessionView id={id} />;
}
