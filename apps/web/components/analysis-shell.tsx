"use client";

import {
  Activity,
  CircleHelp,
  Download,
  GitCompareArrows,
  GitFork,
  Info,
  LayoutDashboard,
  Map,
  RotateCcw,
  Shapes,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brand } from "./brand";
import type { AnalysisSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/format";

const navItems = [
  { label: "Overview", path: "", Icon: LayoutDashboard },
  { label: "Forks", path: "forks", Icon: GitFork },
  { label: "Evolution", path: "evolution", Icon: Map },
  { label: "Directions", path: "directions", Icon: Shapes },
  { label: "Compare", path: "compare", Icon: GitCompareArrows },
];

export function AnalysisShell({
  analysis,
  connection,
  children,
}: {
  analysis: AnalysisSummary;
  connection?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const base = `/analyses/${encodeURIComponent(analysis.id)}`;
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <Brand compact />
        </div>
        <div className="topbar-repo">
          <div className="repo-title">
            <GitFork aria-hidden="true" size={20} />
            <span>{analysis.repository}</span>
          </div>
          <div className="analysis-live" aria-live="polite">
            <i
              className={`status-dot ${connection === "live" ? "live" : "warning"}`}
            />
            <span>
              <strong>{statusLabel(analysis.status)}</strong>
              {analysis.progress}% · {analysis.stage}
            </span>
          </div>
        </div>
        <div className="topbar-actions">
          <details className="export-menu">
            <summary className="button">
              <Download aria-hidden="true" size={16} />
              <span>Export</span>
            </summary>
            <div className="export-popover">
              <a href={api.exportUrl(analysis.id, "json")}>JSON analysis</a>
              <a href={api.exportUrl(analysis.id, "csv")}>CSV fork table</a>
              <a href={api.exportUrl(analysis.id, "markdown")}>
                Markdown report
              </a>
            </div>
          </details>
          <Link
            className="icon-button"
            href="/methodology"
            aria-label="Open methodology"
          >
            <CircleHelp size={18} />
          </Link>
        </div>
      </header>
      <nav
        className="mobile-workspace-nav"
        aria-label="Mobile workspace navigation"
      >
        {navItems.map(({ label, path, Icon }) => {
          const href = path ? `${base}/${path}` : base;
          const active = path
            ? pathname.includes(`/${path}`)
            : pathname === base;
          return (
            <Link
              key={label}
              href={href}
              className={active ? "active" : ""}
              aria-current={active ? "page" : undefined}
            >
              <Icon aria-hidden="true" size={17} />
              <span>{label}</span>
            </Link>
          );
        })}
        <Link href="/methodology">
          <Info aria-hidden="true" size={17} />
          <span>Method</span>
        </Link>
      </nav>
      <div className="shell-body">
        <aside className="stage-rail" aria-label="Analysis navigation">
          <section className="rail-section">
            <h2 className="rail-heading">Analysis stages</h2>
            <ol className="stage-list">
              {analysis.stages.map((stage) => (
                <li className="stage-row" key={stage.id}>
                  <StageIcon status={stage.status} />
                  <span>
                    {stage.label}
                    {stage.detail ? (
                      <small className="muted">{stage.detail}</small>
                    ) : null}
                  </span>
                  {stage.progress != null ? (
                    <strong>{stage.progress}%</strong>
                  ) : null}
                </li>
              ))}
            </ol>
          </section>
          <nav className="rail-section" aria-label="Workspace">
            <h2 className="rail-heading">Navigation</h2>
            <ul className="nav-list">
              {navItems.map(({ label, path, Icon }) => {
                const href = path ? `${base}/${path}` : base;
                const active = path
                  ? pathname.includes(`/${path}`)
                  : pathname === base;
                return (
                  <li key={label}>
                    <Link
                      className={`nav-link ${active ? "active" : ""}`}
                      href={href}
                      aria-current={active ? "page" : undefined}
                    >
                      <Icon aria-hidden="true" size={16} />
                      {label}
                    </Link>
                  </li>
                );
              })}
              <li>
                <Link className="nav-link" href="/methodology">
                  <Info aria-hidden="true" size={16} />
                  Methodology
                </Link>
              </li>
            </ul>
          </nav>
          <div className="quota-card">
            <div>
              <span>Sampling & limits</span>
              <strong
                className={analysis.isSampled ? "tone-warning" : "tone-good"}
              >
                {analysis.isSampled ? "Sampled" : "Complete"}
              </strong>
            </div>
            <div>
              <span>API quota</span>
              <strong>{analysis.rateLimitRemainingPercent ?? "—"}%</strong>
            </div>
            <div>
              <span>Forks analyzed</span>
              <strong>{formatNumber(analysis.analyzedForks)}</strong>
            </div>
          </div>
        </aside>
        {children}
      </div>
    </div>
  );
}

function statusLabel(status: AnalysisSummary["status"]): string {
  return {
    queued: "Analysis queued",
    running: "Analysis in progress",
    cancelling: "Cancelling analysis",
    partial: "Partial results",
    completed: "Analysis complete",
    failed: "Analysis failed",
    cancelled: "Analysis cancelled",
  }[status];
}

function StageIcon({
  status,
}: {
  status: AnalysisSummary["stages"][number]["status"];
}) {
  if (status === "complete")
    return (
      <span className="tone-good" aria-label="Complete">
        ●
      </span>
    );
  if (status === "active")
    return (
      <Activity className="tone-good" aria-label="In progress" size={15} />
    );
  if (status === "warning")
    return (
      <RotateCcw className="tone-warning" aria-label="Waiting" size={15} />
    );
  if (status === "failed")
    return (
      <span className="tone-error" aria-label="Failed">
        ●
      </span>
    );
  return (
    <span className="muted" aria-label="Queued">
      ○
    </span>
  );
}
