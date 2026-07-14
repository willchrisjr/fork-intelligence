"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Copy,
  Download,
  ExternalLink,
  GitCommitHorizontal,
  GitCompareArrows,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";

const colors = ["#0b57e3", "#078a7b", "#6938d3"];

export function ComparisonPage({ comparisonId }: { comparisonId: string }) {
  const query = useQuery({
    queryKey: ["comparison", comparisonId],
    queryFn: ({ signal }) => api.getComparison(comparisonId, signal),
  });
  if (query.isLoading)
    return (
      <main id="main-content" className="state-panel">
        <p>Loading comparison…</p>
      </main>
    );
  if (!query.data)
    return (
      <main id="main-content" className="state-panel">
        <div>
          <AlertTriangle size={36} />
          <h1>Comparison unavailable</h1>
          <p>The API did not return this comparison.</p>
          <button className="button" onClick={() => query.refetch()}>
            Try again
          </button>
        </div>
      </main>
    );
  const comparison = query.data;
  return (
    <div className="comparison-shell">
      <aside className="comparison-nav">
        <strong>
          Fork
          <br />
          Intelligence
        </strong>
        <a className="active" href="#summary">
          <GitCompareArrows size={18} />
          Compare
        </a>
        <a href={`/analyses/${comparison.analysisId}`}>Forks</a>
        <a href="/methodology">Methodology</a>
      </aside>
      <main id="main-content" className="comparison-main">
        <header className="comparison-topbar">
          <strong className="mono">Comparison</strong>
          <div>
            <button
              className="button"
              onClick={() => navigator.clipboard?.writeText(location.href)}
            >
              <Copy size={15} />
              Copy link
            </button>
            <a
              className="button"
              href={api.exportUrl(comparison.analysisId, "markdown")}
            >
              <Download size={15} />
              Export report
            </a>
            <a
              className="icon-button"
              href="/methodology"
              aria-label="Methodology"
            >
              <CircleHelp size={17} />
            </a>
          </div>
        </header>
        <section
          className="comparison-repositories"
          aria-label="Compared repositories"
        >
          {comparison.repositories.map((repository, index) => (
            <article
              key={repository.id}
              style={{ "--repo-color": colors[index] } as React.CSSProperties}
            >
              <span>{repository.role.replace("_", " ")}</span>
              <strong>{repository.fullName}</strong>
              <footer>
                <span className="mono">{repository.branch}</span>
                <span className="mono">{repository.headSha ?? "unknown"}</span>
                <time>{formatDate(repository.updatedAt)}</time>
              </footer>
            </article>
          ))}
        </section>
        <nav className="page-tabs" aria-label="Comparison sections">
          <a className="active" href="#summary">
            Summary
          </a>
          <a href="#history">History</a>
          <a href="#patches">Patches</a>
          <a href="#composition">Files</a>
          <a href="#integration">Integration</a>
          <a href="#evidence">Evidence</a>
        </nav>
        <div className="comparison-grid" id="summary">
          <div className="comparison-left">
            <section className="relationship" id="history">
              <h2>Git history relationship</h2>
              <div className="history-columns">
                {comparison.repositories.map((repository, index) => (
                  <div key={repository.id}>
                    <h3 style={{ color: colors[index] }}>
                      {repository.role.replace("_", " ")}
                    </h3>
                    <div className="history-line">
                      {[
                        repository.headSha ?? "head",
                        "merge base",
                        "earlier",
                      ].map((sha, commitIndex) => (
                        <div
                          className="history-commit"
                          key={sha + commitIndex}
                          style={
                            {
                              "--repo-color": colors[index],
                            } as React.CSSProperties
                          }
                        >
                          <span />
                          <p>
                            <strong className="mono">
                              {commitIndex === 0 ? sha.slice(0, 8) : sha}
                            </strong>
                            <small>
                              {commitIndex === 0
                                ? "Selected head"
                                : commitIndex === 1
                                  ? "Common ancestor"
                                  : "Earlier history"}
                            </small>
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
            <div className="comparison-lower">
              <section className="section-panel" id="patches">
                <h2>Change overlap</h2>
                <table className="matrix">
                  <thead>
                    <tr>
                      <th />
                      <th colSpan={comparison.repositories.length}>
                        Compared repository
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.repositories.map((repository) => (
                      <tr key={repository.id}>
                        <th>{repository.role.replace("_", " ")}</th>
                        {comparison.repositories.map((other) => {
                          const cell = comparison.overlap.find(
                            (item) =>
                              (item.leftId === repository.id &&
                                item.rightId === other.id) ||
                              (item.rightId === repository.id &&
                                item.leftId === other.id),
                          );
                          return (
                            <td key={other.id}>
                              {repository.id === other.id ? (
                                "—"
                              ) : cell ? (
                                <>
                                  <strong>{cell.percent.toFixed(0)}%</strong>
                                  <small>
                                    {cell.count} {cell.basis}
                                  </small>
                                </>
                              ) : (
                                "Unknown"
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted">
                  The basis is shown per comparison. Changed-path overlap is an
                  integration approximation, not patch equivalence.
                </p>
              </section>
              <section className="section-panel" id="composition">
                <h2>Change composition</h2>
                {comparison.composition.map((category) => (
                  <div className="composition-row" key={category.category}>
                    <strong>{category.category.replaceAll("_", " ")}</strong>
                    {comparison.repositories.map((repository, index) => (
                      <span
                        key={repository.id}
                        style={
                          {
                            "--bar": `${category.values[repository.id] ?? 0}%`,
                            "--repo-color": colors[index],
                          } as React.CSSProperties
                        }
                      >
                        {category.values[repository.id] ?? 0}%
                      </span>
                    ))}
                  </div>
                ))}
              </section>
              <section className="section-panel" id="integration">
                <h2>Integration considerations</h2>
                <ul className="integration-list">
                  {comparison.integration.map((item) => (
                    <li key={item.label}>
                      {item.status === "good" ? (
                        <CheckCircle2 className="tone-good" />
                      ) : item.status === "warning" ? (
                        <AlertTriangle className="tone-warning" />
                      ) : (
                        <CircleHelp className="muted" />
                      )}
                      <span>
                        <strong>{item.label}</strong>
                        <small>{item.detail}</small>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
          <aside className="comparison-evidence" id="evidence">
            <h2>
              Evidence <span>{comparison.evidence.length}</span>
            </h2>
            <ul>
              {comparison.evidence.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.summary}</p>
                  </div>
                  <span>{item.provenance}</span>
                  {item.sourceUrl ? (
                    <a
                      href={item.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Open source for ${item.title}`}
                    >
                      <ExternalLink size={15} />
                    </a>
                  ) : (
                    <GitCommitHorizontal size={15} />
                  )}
                </li>
              ))}
            </ul>
            {comparison.missingData.length ? (
              <div className="banner">
                <AlertTriangle size={15} />
                <span>
                  <strong>Missing data</strong>
                  <br />
                  {comparison.missingData.join("; ")}
                </span>
              </div>
            ) : null}
          </aside>
        </div>
      </main>
    </div>
  );
}
