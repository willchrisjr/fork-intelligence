"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Braces,
  GitCompareArrows,
  Network,
  Route,
  Sparkles,
} from "lucide-react";
import { AnalysisShell } from "./analysis-shell";
import { Confidence } from "./confidence";
import { api } from "@/lib/api";

export function DirectionsPage({ analysisId }: { analysisId: string }) {
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: ({ signal }) => api.getAnalysis(analysisId, signal),
  });
  const clusters = useQuery({
    queryKey: ["clusters", analysisId],
    queryFn: ({ signal }) => api.getClusters(analysisId, signal),
    enabled: Boolean(analysis.data),
  });
  if (!analysis.data)
    return (
      <main id="main-content" className="state-panel">
        <p>Loading development directions…</p>
      </main>
    );
  return (
    <AnalysisShell analysis={analysis.data}>
      <main className="workspace" id="main-content">
        <div className="workspace-main directions-page">
          <header className="page-heading">
            <div>
              <h1>Development directions</h1>
              <p>
                Deterministic groups of forks with shared paths, technologies,
                patches, and change patterns.
              </p>
            </div>
            <a
              className="button"
              href={`/analyses/${analysisId}/evolution?graphMode=cluster`}
            >
              <Network size={16} />
              View cluster graph
            </a>
          </header>
          <div className="banner info">
            <Sparkles size={16} />
            <span>
              Labels are{" "}
              {clusters.data?.items.some(
                (item) => item.labelMethod === "ai_evidence_grounded",
              )
                ? "evidence-grounded AI enrichment where noted"
                : "heuristic"}
              . Cluster membership remains deterministic and inspectable.
            </span>
          </div>
          {clusters.isError ? (
            <div className="state-panel">
              <div>
                <AlertTriangle size={34} />
                <h2>Directions unavailable</h2>
                <p>
                  Clustering has not completed or the result could not be
                  loaded.
                </p>
                <button className="button" onClick={() => clusters.refetch()}>
                  Try again
                </button>
              </div>
            </div>
          ) : clusters.data?.items.length ? (
            <div className="cluster-list">
              {clusters.data.items.map((cluster, index) => (
                <article className="cluster-row" key={cluster.id}>
                  <div className="cluster-index">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div className="cluster-copy">
                    <span className="cluster-method">
                      {cluster.labelMethod === "heuristic"
                        ? "Heuristic label"
                        : "AI label · evidence grounded"}
                    </span>
                    <h2>{cluster.label}</h2>
                    <p>
                      {cluster.summary ||
                        "This direction has not received a human-readable summary yet."}
                    </p>
                    <div className="cluster-facts">
                      <span>
                        <Route size={14} />
                        {cluster.memberCount} member forks
                      </span>
                      <span>
                        <Braces size={14} />
                        {cluster.method}
                      </span>
                    </div>
                  </div>
                  <div className="cluster-signals">
                    <div>
                      <small>Confidence</small>
                      <Confidence value={cluster.confidence} />
                    </div>
                    <div>
                      <small>Shared paths</small>
                      <p className="mono">
                        {cluster.sharedPaths.length
                          ? cluster.sharedPaths.slice(0, 3).join(" · ")
                          : "Awaiting deep analysis"}
                      </p>
                    </div>
                    <div>
                      <small>Shared technologies</small>
                      <p>
                        {cluster.sharedTechnologies.length
                          ? cluster.sharedTechnologies.slice(0, 4).join(", ")
                          : "Unavailable"}
                      </p>
                    </div>
                  </div>
                  <div className="cluster-actions">
                    <a
                      className="button"
                      href={`/analyses/${analysisId}/evolution?graphMode=cluster&graphSearch=${encodeURIComponent(cluster.label)}`}
                    >
                      Inspect members <ArrowRight size={15} />
                    </a>
                    <a
                      className="button"
                      href={`/analyses/${analysisId}?classification=independent_direction`}
                    >
                      <GitCompareArrows size={15} />
                      Choose forks
                    </a>
                  </div>
                </article>
              ))}
            </div>
          ) : clusters.data ? (
            <div className="state-panel">
              <div>
                <Route size={34} />
                <h2>No directions yet</h2>
                <p>
                  Clustering begins after enough structurally analyzed forks are
                  available. Partial fork results remain accessible.
                </p>
                <a className="button" href={`/analyses/${analysisId}`}>
                  Return to forks
                </a>
              </div>
            </div>
          ) : (
            <div className="state-panel">
              <p>Loading clusters…</p>
            </div>
          )}
        </div>
      </main>
    </AnalysisShell>
  );
}
