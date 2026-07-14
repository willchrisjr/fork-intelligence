import { Suspense } from "react";
import { EvolutionPage } from "@/components/evolution-page";

export default async function Page({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return (
    <Suspense fallback={<main>Loading…</main>}>
      <EvolutionPage analysisId={analysisId} />
    </Suspense>
  );
}
