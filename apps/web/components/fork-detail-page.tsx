"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ExternalLink,
  GitCommitHorizontal,
  GitMerge,
  GitPullRequestArrow,
  Layers3,
} from "lucide-react";
import { AnalysisShell } from "./analysis-shell";
import { Confidence } from "./confidence";
import { api } from "@/lib/api";
import {
  classificationLabel,
  formatDate,
  formatNumber,
  formatPercent,
} from "@/lib/format";

export function ForkDetailPage({
  analysisId,
  repositoryId,
}: {
  analysisId: string;
  repositoryId: string;
}) {
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: ({ signal }) => api.getAnalysis(analysisId, signal),
  });
  const detail = useQuery({
    queryKey: ["fork", analysisId, repositoryId],
    queryFn: ({ signal }) => api.getFork(analysisId, repositoryId, signal),
  });
  if (analysis.isLoading || detail.isLoading)
    return (
      <main id="main-content" className="state-panel">
        <p>Loading fork evidence…</p>
      </main>
    );
  if (!analysis.data || !detail.data)
    return (
      <main id="main-content" className="state-panel">
        <div>
          <AlertTriangle size={36} />
          <h1>Fork evidence unavailable</h1>
          <p>The analysis did not return this repository.</p>
        </div>
      </main>
    );
  const fork = detail.data;
  return (
    <AnalysisShell analysis={analysis.data}>
      <main className="workspace" id="main-content">
        <div className="workspace-main detail-page">
          <header className="detail-heading">
            <div>
              <a
                className="mono detail-repository"
                href={fork.url}
                target="_blank"
                rel="noreferrer"
              >
                {fork.fullName} <ExternalLink size={15} />
              </a>
              <h1>{classificationLabel(fork.classification)}</h1>
              <p>
                {fork.description ??
                  "Evidence-backed fork details and relationship to upstream."}
              </p>
            </div>
            <div className="detail-confidence">
              <span>Confidence</span>
              <Confidence value={fork.confidence} />
              <small>
                {formatPercent(fork.dataCoverage)} data coverage ·{" "}
                {fork.analysisDepth}
              </small>
            </div>
          </header>
          {fork.missingData.length ? (
            <div className="banner">
              <AlertTriangle size={16} />
              <span>
                Some evidence is unavailable: {fork.missingData.join("; ")}.
              </span>
            </div>
          ) : null}
          <div className="detail-stat-grid">
            <Stat
              icon={<GitCommitHorizontal />}
              label="Unique commits"
              value={formatNumber(fork.uniqueCommits)}
            />
            <Stat
              icon={<GitPullRequestArrow />}
              label="Unique patches"
              value={formatNumber(fork.uniquePatches)}
            />
            <Stat
              icon={<GitMerge />}
              label="Ahead / behind"
              value={`${formatNumber(fork.ahead)} / ${formatNumber(fork.behind)}`}
            />
            <Stat
              icon={<Layers3 />}
              label="Original work"
              value={formatPercent(fork.originalWorkPercent, 1)}
            />
          </div>
          <div className="detail-columns">
            <section className="section-panel">
              <h2>Why this classification</h2>
              <ul className="reason-list">
                {fork.classificationReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              <h2>History relationship</h2>
              <dl className="detail-list">
                <div>
                  <dt>Default branch</dt>
                  <dd className="mono">{fork.defaultBranch}</dd>
                </div>
                <div>
                  <dt>Head commit</dt>
                  <dd className="mono">{fork.headSha ?? "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Merge base</dt>
                  <dd className="mono">{fork.mergeBase ?? "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Last updated</dt>
                  <dd>{formatDate(fork.updatedAt)}</dd>
                </div>
                <div>
                  <dt>Cluster</dt>
                  <dd>{fork.cluster?.label ?? "Not assigned"}</dd>
                </div>
              </dl>
            </section>
            <section className="section-panel">
              <h2>Score components</h2>
              <table className="score-table wide">
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>Raw value</th>
                    <th>Weight</th>
                    <th>Contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {fork.scoreComponents.map((component) => (
                    <tr key={component.key}>
                      <td>{component.label}</td>
                      <td>
                        {component.missing
                          ? "Missing"
                          : String(component.value ?? "—")}
                      </td>
                      <td>{component.weight?.toFixed(2) ?? "—"}</td>
                      <td>{component.contribution?.toFixed(3) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
          <section className="section-panel">
            <h2>Evidence</h2>
            <div className="evidence-grid">
              {fork.evidence.map((item) => (
                <article key={item.id} className="evidence-card">
                  <div>
                    <span className="evidence-type">{item.type}</span>
                    <span className="mono">{item.reference}</span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.summary}</p>
                  <footer>
                    <span>{item.provenance}</span>
                    {item.sourceUrl ? (
                      <a href={item.sourceUrl} target="_blank" rel="noreferrer">
                        Open source <ExternalLink size={12} />
                      </a>
                    ) : null}
                  </footer>
                </article>
              ))}
            </div>
          </section>
        </div>
      </main>
    </AnalysisShell>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="detail-stat">
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}
