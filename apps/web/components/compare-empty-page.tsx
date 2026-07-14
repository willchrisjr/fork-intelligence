"use client";

import { useQuery } from "@tanstack/react-query";
import { GitCompareArrows } from "lucide-react";
import { AnalysisShell } from "./analysis-shell";
import { api } from "@/lib/api";

export function CompareEmptyPage({ analysisId }: { analysisId: string }) {
  const query = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: ({ signal }) => api.getAnalysis(analysisId, signal),
  });
  if (!query.data)
    return (
      <main id="main-content" className="state-panel">
        <p>Loading comparison selection…</p>
      </main>
    );
  return (
    <AnalysisShell analysis={query.data}>
      <main className="workspace" id="main-content">
        <div className="workspace-main">
          <div className="state-panel">
            <div>
              <GitCompareArrows size={40} />
              <h1>Compare upstream with two forks</h1>
              <p>
                Select exactly two forks in the fork table. The resolved
                upstream repository is included automatically as the comparison
                baseline.
              </p>
              <a
                className="button button-primary"
                href={`/analyses/${analysisId}`}
              >
                Choose two forks
              </a>
            </div>
          </div>
        </div>
      </main>
    </AnalysisShell>
  );
}
