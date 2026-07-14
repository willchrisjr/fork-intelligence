import { ForkDetailPage } from "@/components/fork-detail-page";

export default async function ForkPage({
  params,
}: {
  params: Promise<{ analysisId: string; repositoryId: string }>;
}) {
  const { analysisId, repositoryId } = await params;
  return <ForkDetailPage analysisId={analysisId} repositoryId={repositoryId} />;
}
