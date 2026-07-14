import { redirect } from "next/navigation";

export default async function ForksPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  redirect(`/analyses/${encodeURIComponent(analysisId)}`);
}
