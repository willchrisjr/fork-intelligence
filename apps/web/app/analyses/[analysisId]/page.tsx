import { Suspense } from "react";
import { AnalysisWorkspace } from "@/components/analysis-workspace";

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return (
    <Suspense fallback={<main id="main-content">Loading analysis…</main>}>
      <AnalysisWorkspace analysisId={analysisId} />
    </Suspense>
  );
}
