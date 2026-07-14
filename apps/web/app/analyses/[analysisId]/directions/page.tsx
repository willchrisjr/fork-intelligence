import { DirectionsPage } from "@/components/directions-page";

export default async function Page({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return <DirectionsPage analysisId={analysisId} />;
}
