"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  GitCompareArrows,
  RotateCw,
  Search,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useDeferredValue } from "react";
import { AnalysisShell } from "./analysis-shell";
import { EvidenceInspector } from "./evidence-inspector";
import { ForkTable } from "./fork-table";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { useProgressStream } from "@/lib/use-progress-stream";
import { useWorkspaceState } from "@/lib/use-workspace-state";

export function AnalysisWorkspace({ analysisId }: { analysisId: string }) {
  const router = useRouter();
  const { state, update } = useWorkspaceState();
  const deferredQuery = useDeferredValue(state.q);
  const analysisQuery = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: ({ signal }) => api.getAnalysisOverview(analysisId, signal),
  });
  const progress = useProgressStream(analysisId, analysisQuery.data);
  const analysis = progress.analysis ?? analysisQuery.data;
  const forksQuery = useQuery({
    queryKey: [
      "forks",
      analysisId,
      deferredQuery,
      state.sort,
      state.order,
      state.classification,
      state.depth,
      state.cursor,
    ],
    queryFn: ({ signal }) =>
      api.getForks(
        analysisId,
        {
          cursor: state.cursor,
          pageSize: 25,
          q: deferredQuery,
          sort: state.sort,
          order: state.order,
          classification: state.classification,
          depth: state.depth,
        },
        signal,
      ),
    enabled: Boolean(analysis),
    placeholderData: (previous) => previous,
  });
  const detailQuery = useQuery({
    queryKey: ["fork", analysisId, state.evidence],
    queryFn: ({ signal }) => api.getFork(analysisId, state.evidence, signal),
    enabled: Boolean(state.evidence),
  });
  const comparison = useMutation({
    mutationFn: async () => {
      const upstreamId =
        analysis?.rootRepositoryId ?? (await api.getUpstreamId(analysisId));
      return api.createComparison(analysisId, [upstreamId, ...state.selected]);
    },
    onSuccess: (result) =>
      router.push(`/comparisons/${encodeURIComponent(result.id)}`),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelAnalysis(analysisId),
  });
  const resume = useMutation({
    mutationFn: () => api.resumeAnalysis(analysisId),
  });

  if (!analysis) {
    if (analysisQuery.isError)
      return (
        <StandaloneError
          error={analysisQuery.error}
          retry={() => analysisQuery.refetch()}
        />
      );
    return <WorkspaceLoading />;
  }

  const partial = analysis.status === "partial" || forksQuery.data?.partial;
  const rateLimited = analysis.warnings.some((warning) =>
    warning.toLowerCase().includes("rate limit"),
  );
  const hasInspector = Boolean(state.evidence);

  return (
    <AnalysisShell analysis={analysis} connection={progress.connection}>
      <main
        className={`workspace ${hasInspector ? "has-inspector" : ""}`}
        id="main-content"
      >
        <div className="workspace-main">
          <div className="workspace-stack">
            <section className="summary-strip" aria-label="Analysis summary">
              <SummaryItem
                label="Forks discovered"
                value={formatNumber(analysis.discoveredForks)}
              />
              <SummaryItem
                label="Shortlisted"
                value={formatNumber(analysis.shortlistedForks)}
              />
              <SummaryItem
                label="Analyzed"
                value={`${formatNumber(analysis.analyzedForks)} (${analysis.progress}%)`}
              />
              <SummaryItem
                label="Pending"
                value={formatNumber(analysis.pendingForks)}
              />
              <SummaryItem
                label="API quota"
                value={
                  analysis.rateLimitRemainingPercent == null
                    ? "Unavailable"
                    : `${analysis.rateLimitRemainingPercent}%`
                }
                warning={rateLimited}
              />
              <SummaryItem
                label="As of"
                value={formatDateTime(analysis.updatedAt)}
              />
            </section>
            {partial || rateLimited ? (
              <div className="banner" role="status">
                <AlertTriangle aria-hidden="true" size={16} />
                <span>
                  <strong>Results are partial.</strong>{" "}
                  {rateLimited
                    ? "GitHub API rate limits are delaying analysis. "
                    : "Analysis is still in progress. "}
                  Scores and coverage may change as evidence arrives.
                </span>
              </div>
            ) : null}
            {progress.connection === "reconnecting" ||
            progress.connection === "error" ? (
              <div className="banner info" role="status">
                Progress updates are{" "}
                {progress.connection === "error" ? "offline" : "reconnecting"}.
                The last known results remain visible.
              </div>
            ) : null}
            <div className="command-bar" aria-label="Fork controls">
              <div className="command-search">
                <Search aria-hidden="true" size={16} />
                <label className="sr-only" htmlFor="fork-search">
                  Search forks
                </label>
                <input
                  id="fork-search"
                  className="field"
                  type="search"
                  placeholder="Search forks"
                  value={state.q}
                  onChange={(event) =>
                    update({ q: event.target.value, page: 1 })
                  }
                />
              </div>
              <label>
                <span className="sr-only">Ranking profile</span>
                <select
                  className="select"
                  value={state.sort}
                  onChange={(event) =>
                    update(
                      {
                        sort: event.target.value as typeof state.sort,
                        page: 1,
                      },
                      true,
                    )
                  }
                >
                  <option value="maintained_successor">
                    Maintained successor
                  </option>
                  <option value="unmerged_innovation">
                    Unmerged innovation
                  </option>
                  <option value="maintenance">Maintenance</option>
                  <option value="original_development">
                    Original development
                  </option>
                  <option value="recent_activity">Recent activity</option>
                  <option value="adoption">Adoption</option>
                  <option value="unique_patches">Unique patches</option>
                  <option value="name">Repository name</option>
                </select>
              </label>
              <label>
                <span className="sr-only">Analysis depth filter</span>
                <select
                  className="select"
                  value={state.depth}
                  onChange={(event) =>
                    update(
                      {
                        depth: event.target.value as typeof state.depth,
                        page: 1,
                      },
                      true,
                    )
                  }
                >
                  <option value="">All depths</option>
                  <option value="deep">Deep analysis</option>
                  <option value="structural">Structural</option>
                  <option value="metadata">Metadata only</option>
                </select>
              </label>
              <button
                className="button"
                type="button"
                title="Classification filters are encoded in the shareable URL"
                onClick={() =>
                  update(
                    {
                      classification: state.classification
                        ? ""
                        : "maintained_continuation",
                      cursor: "",
                      page: 1,
                    },
                    true,
                  )
                }
              >
                <SlidersHorizontal size={15} /> Filters{" "}
                {state.classification ? "1" : ""}
              </button>
              <span className="selection-count" aria-live="polite">
                {state.selected.length} of 2 forks selected · upstream included
              </span>
              <button
                className="button button-primary"
                disabled={state.selected.length !== 2 || comparison.isPending}
                onClick={() => comparison.mutate()}
              >
                <GitCompareArrows size={16} />
                {comparison.isPending ? "Creating…" : "Compare selected"}
              </button>
              {analysis.status === "running" ||
              analysis.status === "partial" ? (
                <button
                  className="button button-danger"
                  onClick={() => cancel.mutate()}
                  disabled={cancel.isPending}
                >
                  <XCircle size={16} />
                  Cancel
                </button>
              ) : analysis.status === "failed" ||
                analysis.status === "cancelled" ? (
                <button
                  className="button"
                  onClick={() => resume.mutate()}
                  disabled={resume.isPending}
                >
                  <RotateCw size={16} />
                  Resume
                </button>
              ) : null}
            </div>
            {comparison.error ? (
              <div className="banner error" role="alert">
                The comparison could not be created. Keep the selection and try
                again.
              </div>
            ) : null}
            {forksQuery.isError ? (
              <DataError
                error={forksQuery.error}
                retry={() => forksQuery.refetch()}
              />
            ) : forksQuery.data ? (
              forksQuery.data.items.length ? (
                <ForkTable
                  page={forksQuery.data}
                  analysisId={analysisId}
                  selected={state.selected}
                  sort={state.sort}
                  order={state.order}
                  onSort={(sort, order) =>
                    update(
                      { sort: sort as typeof state.sort, order, page: 1 },
                      true,
                    )
                  }
                  onSelect={(id) =>
                    update(
                      {
                        selected: state.selected.includes(id)
                          ? state.selected.filter((item) => item !== id)
                          : state.selected.length < 2
                            ? [...state.selected, id]
                            : state.selected,
                      },
                      true,
                    )
                  }
                  onInspect={(id) => update({ evidence: id }, true)}
                  onPage={(page) =>
                    update(
                      page === 1
                        ? { page: 1, cursor: "" }
                        : { page, cursor: forksQuery.data?.nextCursor ?? "" },
                      true,
                    )
                  }
                />
              ) : (
                <div className="state-panel">
                  <div>
                    <Search size={34} />
                    <h2>No forks match these controls</h2>
                    <p>
                      Clear the search or filters. The analysis may still be
                      discovering forks.
                    </p>
                    <button
                      className="button"
                      onClick={() =>
                        update(
                          { q: "", classification: "", depth: "", page: 1 },
                          true,
                        )
                      }
                    >
                      Reset controls
                    </button>
                  </div>
                </div>
              )
            ) : (
              <TableLoading />
            )}
          </div>
        </div>
        {hasInspector ? (
          <EvidenceInspector
            detail={detailQuery.data}
            isLoading={detailQuery.isLoading}
            onClose={() => update({ evidence: "" }, true)}
            analysisId={analysisId}
          />
        ) : null}
      </main>
    </AnalysisShell>
  );
}

function SummaryItem({
  label,
  value,
  warning,
}: {
  label: string;
  value: string;
  warning?: boolean;
}) {
  return (
    <div className="summary-item">
      <small>{label}</small>
      <strong className={warning ? "tone-warning" : undefined}>{value}</strong>
    </div>
  );
}

function WorkspaceLoading() {
  return (
    <main id="main-content" style={{ padding: 32 }}>
      <div className="skeleton" style={{ width: 220, height: 28 }} />
      <div
        className="skeleton"
        style={{ width: "100%", height: 420, marginTop: 24 }}
      />
    </main>
  );
}

function TableLoading() {
  return (
    <div
      className="data-panel"
      aria-label="Loading fork results"
      style={{ padding: 14 }}
    >
      {Array.from({ length: 8 }, (_, index) => (
        <div
          key={index}
          className="skeleton"
          style={{ height: 42, marginBottom: 8 }}
        />
      ))}
    </div>
  );
}

function StandaloneError({
  error,
  retry,
}: {
  error: Error;
  retry: () => unknown;
}) {
  return (
    <main
      id="main-content"
      className="state-panel"
      style={{ minHeight: "100dvh", border: 0 }}
    >
      <div>
        <AlertTriangle className="tone-error" size={38} />
        <h1>Analysis unavailable</h1>
        <p>
          {error instanceof ApiError
            ? error.payload.message
            : "The API did not return this analysis."}
        </p>
        <button className="button" onClick={retry}>
          Try again
        </button>
      </div>
    </main>
  );
}

function DataError({ error, retry }: { error: Error; retry: () => unknown }) {
  const rateLimited = error instanceof ApiError && error.status === 429;
  return (
    <div className="state-panel">
      <div>
        <AlertTriangle
          className={rateLimited ? "tone-warning" : "tone-error"}
          size={34}
        />
        <h2>
          {rateLimited
            ? "Fork results are rate limited"
            : "Fork results unavailable"}
        </h2>
        <p>
          {error instanceof ApiError
            ? error.payload.message
            : "The fork table could not be loaded."}{" "}
          Existing analysis progress is preserved.
        </p>
        <button className="button" onClick={retry}>
          Retry results
        </button>
      </div>
    </div>
  );
}
