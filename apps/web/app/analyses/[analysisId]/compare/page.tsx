import { CompareEmptyPage } from "@/components/compare-empty-page";

export default async function Page({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return <CompareEmptyPage analysisId={analysisId} />;
}
