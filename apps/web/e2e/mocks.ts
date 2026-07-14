import type { Page, Route } from "@playwright/test";

const NOW = "2026-07-13T18:30:00Z";

type Json = Record<string, unknown>;

export interface MockApiOptions {
  analysis?: Json;
  createError?: { status: number; message: string };
  analysisError?: { status: number; message: string };
  forksError?: { status: number; message: string };
  partialForks?: boolean;
}

export interface MockApiLog {
  createdAnalyses: Json[];
  createdComparisons: Json[];
  cancelled: number;
  resumed: number;
  exportRequests: string[];
}

export const forkOne = {
  id: "repo-a",
  is_fork: true,
  owner: "lab",
  name: "next",
  html_url: "https://github.com/lab/next",
  default_branch: "main",
  depth: "deep",
  metadata: {
    description: "A maintained continuation with focused reliability work.",
    updated_at: "2026-07-12T12:00:00Z",
    releases_count: 4,
  },
  metrics: {
    maintenance_state: "actively_maintained",
    original_work_percent: 42.5,
    activity_30d: 14,
    activity_90d: 31,
    unique_commits: 27,
    unique_patches: 19,
    confidence: 0.93,
    data_coverage: 96,
    evidence_commits: 27,
    evidence_patches: 19,
    evidence_files: 38,
    evidence_releases: 4,
    head_sha: "f00dbabe1234567890",
    merge_base: "abc123450000000000",
    ahead: 27,
    behind: 3,
    cluster_id: "cluster-runtime",
    cluster_label: "Runtime reliability",
    cluster_confidence: 0.88,
    missing_data: [],
  },
  classification: {
    label: "maintained_continuation",
    confidence: 0.93,
    reasons: [
      "Sustained development across multiple recent windows.",
      "Nineteen patches are not present upstream.",
    ],
  },
  scores: [
    {
      dimension: "maintenance",
      label: "Maintenance",
      raw_value: 88,
      normalized_value: 0.88,
      weight: 0.3,
      contribution: 0.264,
      missing: false,
    },
    {
      dimension: "original_development",
      label: "Original development",
      raw_value: 42.5,
      normalized_value: 0.425,
      weight: 0.15,
      contribution: 0.064,
      missing: false,
    },
  ],
  evidence: [
    {
      id: "ev-patch",
      type: "patch",
      title: "Retry-safe transaction patch",
      summary: "Stable patch evidence shows a retry path absent from upstream.",
      provenance: "git",
      source_url: "https://github.com/lab/next/commit/f00dbabe",
      reference: "f00dbabe",
      confidence: 0.96,
      retrieved_at: NOW,
    },
    {
      id: "ev-release",
      type: "release",
      title: "Release v2.4.0",
      summary: "A recent tagged release documents ongoing maintenance.",
      provenance: "github",
      source_url: "https://github.com/lab/next/releases/tag/v2.4.0",
      reference: "v2.4.0",
      confidence: 1,
      retrieved_at: NOW,
    },
  ],
};

export const forkTwo = {
  id: "repo-b",
  is_fork: true,
  owner: "signal",
  name: "edge",
  html_url: "https://github.com/signal/edge",
  default_branch: "main",
  depth: "structural",
  metadata: { updated_at: "2026-06-28T08:00:00Z", releases_count: 1 },
  metrics: {
    maintenance_state: "maintained",
    original_work_percent: 21,
    activity_30d: 4,
    activity_90d: 12,
    unique_commits: 11,
    unique_patches: 8,
    confidence: 0.77,
    data_coverage: 72,
    evidence_commits: 11,
    evidence_patches: 8,
    evidence_files: 16,
    evidence_releases: 1,
    head_sha: "def678900000000000",
    merge_base: "abc123450000000000",
    ahead: 11,
    behind: 7,
    cluster_id: "cluster-api",
    cluster_label: "API extensions",
    cluster_confidence: 0.72,
    missing_data: ["Binary blob hydration was capped"],
  },
  classification: {
    label: "specialized",
    confidence: 0.77,
    reasons: ["Changes concentrate in API adapters and compatibility code."],
  },
  scores: [
    {
      dimension: "activity",
      label: "Sustained activity",
      raw_value: 54,
      normalized_value: 0.54,
      weight: 0.15,
      contribution: 0.081,
      missing: false,
    },
  ],
  evidence: [
    {
      id: "ev-api",
      type: "file",
      title: "API adapter changes",
      summary:
        "Rename-aware file evidence identifies a specialized adapter direction.",
      provenance: "calculated",
      reference: "src/adapters",
      confidence: 0.82,
      retrieved_at: NOW,
    },
  ],
};

export function analysisFixture(overrides: Json = {}): Json {
  return {
    id: "analysis-1",
    requested_identifier: "upstream/project",
    requested_repository_id: "repo-upstream",
    root_repository_id: "repo-upstream",
    status: "running",
    stage: "git_analysis",
    progress: 64,
    created_at: "2026-07-13T18:00:00Z",
    started_at: "2026-07-13T18:00:05Z",
    updated_at: NOW,
    analysis_version: "mvp-1",
    configuration: { analysis_commit: "test-build" },
    sampling: {
      is_sampled: true,
      counts: { discovered: 48, shortlisted: 12, analyzed: 7, pending: 5 },
    },
    quota_snapshot: {
      remaining_percent: 34,
      resets_at: "2026-07-13T19:00:00Z",
    },
    warnings: [],
    ...overrides,
  };
}

export async function installApiMocks(
  page: Page,
  options: MockApiOptions = {},
): Promise<MockApiLog> {
  const log: MockApiLog = {
    createdAnalyses: [],
    createdComparisons: [],
    cancelled: 0,
    resumed: 0,
    exportRequests: [],
  };
  const analysis = analysisFixture(options.analysis);

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/v1/analyses" && request.method() === "POST") {
      if (options.createError)
        return problem(
          route,
          options.createError.status,
          options.createError.message,
        );
      log.createdAnalyses.push(request.postDataJSON() as Json);
      return json(route, analysis, 201);
    }
    if (path === "/api/v1/analyses/analysis-1/events") {
      return route.fulfill({
        status: 200,
        headers: {
          "content-type": "text/event-stream",
          "cache-control": "no-cache",
        },
        body: `id: event-1\nevent: complete\ndata: ${JSON.stringify({ id: "event-1", type: "complete", occurredAt: NOW })}\n\n`,
      });
    }
    if (
      path === "/api/v1/analyses/analysis-1/overview" &&
      request.method() === "GET"
    ) {
      if (options.analysisError)
        return problem(
          route,
          options.analysisError.status,
          options.analysisError.message,
        );
      return json(route, {
        analysis,
        counts: { repositories: 48, shortlisted: 12 },
        rankings: {},
        data_coverage: {
          structural: 7,
          sampling: { is_sampled: true, metadata_cap: 250, deep_cap: 25 },
        },
      });
    }
    if (path === "/api/v1/analyses/analysis-1" && request.method() === "GET") {
      if (options.analysisError)
        return problem(
          route,
          options.analysisError.status,
          options.analysisError.message,
        );
      return json(route, analysis);
    }
    if (
      path === "/api/v1/analyses/analysis-1/cancel" &&
      request.method() === "POST"
    ) {
      log.cancelled += 1;
      return json(route, { ...analysis, status: "cancelled", progress: 64 });
    }
    if (
      path === "/api/v1/analyses/analysis-1/resume" &&
      request.method() === "POST"
    ) {
      log.resumed += 1;
      return json(route, { ...analysis, status: "running" });
    }
    if (
      path === "/api/v1/analyses/analysis-1/forks" &&
      request.method() === "GET"
    ) {
      if (options.forksError)
        return problem(
          route,
          options.forksError.status,
          options.forksError.message,
        );
      const query = (url.searchParams.get("search") ?? "").toLowerCase();
      const classification = url.searchParams.get("classification");
      const depth = url.searchParams.get("depth");
      const allForks = [forkOne, forkTwo];
      const items = allForks.filter((fork) => {
        const matchesQuery =
          !query || `${fork.owner}/${fork.name}`.includes(query);
        const matchesClassification =
          !classification || fork.classification.label === classification;
        const matchesDepth = !depth || fork.depth === depth;
        return matchesQuery && matchesClassification && matchesDepth;
      });
      return json(route, {
        items,
        total: items.length,
        page: 1,
        limit: 25,
        partial: options.partialForks ?? false,
        updated_at: NOW,
        next_cursor: null,
      });
    }
    if (path === "/api/v1/analyses/analysis-1/forks/repo-a")
      return json(route, forkOne);
    if (path === "/api/v1/analyses/analysis-1/forks/repo-b")
      return json(route, forkTwo);
    if (path === "/api/v1/analyses/analysis-1/evolution") {
      return json(route, {
        nodes: [
          {
            repository_id: "repo-upstream",
            full_name: "upstream/project",
            classification: "unknown",
            metrics: {
              confidence: 1,
              original_work_percent: 0,
              activity_30d: 2,
            },
          },
          {
            repository_id: "repo-a",
            full_name: "lab/next",
            classification: "maintained_continuation",
            cluster_id: "cluster-runtime",
            metrics: {
              confidence: 0.93,
              original_work_percent: 42.5,
              activity_30d: 14,
            },
          },
          {
            repository_id: "repo-b",
            full_name: "signal/edge",
            classification: "specialized",
            cluster_id: "cluster-api",
            metrics: {
              confidence: 0.77,
              original_work_percent: 21,
              activity_30d: 4,
            },
          },
        ],
        edges: [
          {
            source_repository_id: "repo-upstream",
            target_repository_id: "repo-a",
            relationship: "fork",
          },
          {
            source_repository_id: "repo-upstream",
            target_repository_id: "repo-b",
            relationship: "fork",
          },
        ],
        sampling: { forks_discovered: 48, forks_capped: true },
      });
    }
    if (path === "/api/v1/analyses/analysis-1/clusters") {
      return json(route, {
        items: [
          {
            id: "cluster-runtime",
            label: "Runtime reliability",
            summary:
              "Forks that concentrate on retries, observability, and runtime safeguards.",
            member_repository_ids: ["repo-a"],
            shared_paths: ["src/runtime", "tests/integration"],
            shared_technologies: ["Python", "PostgreSQL"],
            confidence: 0.88,
            algorithm: "complete-link-v1",
            labeling_method: "heuristic",
          },
          {
            id: "cluster-api",
            label: "API extensions",
            summary:
              "A specialized family of adapter and compatibility changes.",
            member_repository_ids: ["repo-b"],
            shared_paths: ["src/adapters"],
            shared_technologies: ["TypeScript"],
            confidence: 0.72,
            algorithm: "complete-link-v1",
            labeling_method: "heuristic",
          },
        ],
      });
    }
    if (
      path === "/api/v1/analyses/analysis-1/comparisons" &&
      request.method() === "POST"
    ) {
      log.createdComparisons.push(request.postDataJSON() as Json);
      return json(route, comparisonFixture(), 201);
    }
    if (path === "/api/v1/comparisons/comparison-1")
      return json(route, comparisonFixture());
    if (path.startsWith("/api/v1/analyses/analysis-1/exports/")) {
      log.exportRequests.push(path);
      return route.fulfill({
        status: 200,
        contentType: "text/plain",
        body: "deterministic export",
      });
    }

    return problem(route, 404, `No E2E mock for ${request.method()} ${path}`);
  });

  return log;
}

function comparisonFixture(): Json {
  return {
    id: "comparison-1",
    analysis_id: "analysis-1",
    repository_ids: ["repo-upstream", "repo-a", "repo-b"],
    updated_at: NOW,
    result: {
      repositories: [
        {
          id: "repo-upstream",
          full_name: "upstream/project",
          branch: "main",
          head_sha: "abc12345",
          updated_at: NOW,
        },
        {
          id: "repo-a",
          full_name: "lab/next",
          branch: "main",
          head_sha: "f00dbabe",
          updated_at: NOW,
        },
        {
          id: "repo-b",
          full_name: "signal/edge",
          branch: "main",
          head_sha: "def67890",
          updated_at: NOW,
        },
      ],
      overlap: [
        {
          left_id: "repo-upstream",
          right_id: "repo-a",
          percent: 32,
          patches: 12,
        },
        {
          left_id: "repo-upstream",
          right_id: "repo-b",
          percent: 18,
          patches: 7,
        },
        { left_id: "repo-a", right_id: "repo-b", percent: 41, patches: 9 },
      ],
      composition: [
        {
          category: "Source",
          values: { "repo-upstream": 20, "repo-a": 58, "repo-b": 44 },
        },
        {
          category: "Tests",
          values: { "repo-upstream": 10, "repo-a": 31, "repo-b": 20 },
        },
      ],
      integration: [
        {
          label: "Patch overlap",
          status: "good",
          detail: "Stable patches make reuse evidence inspectable.",
        },
        {
          label: "Merge conflicts",
          status: "warning",
          detail: "Conflict approximation flags two overlapping paths.",
        },
      ],
      evidence: [
        {
          id: "ev-comparison",
          type: "patch",
          title: "Shared retry patch",
          summary: "Both forks contain the same stable patch fingerprint.",
          provenance: "git",
          source_url: "https://github.com/lab/next/commit/f00dbabe",
          retrieved_at: NOW,
        },
      ],
      missing_data: ["Binary similarity was not calculated"],
    },
  };
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function problem(route: Route, status: number, message: string) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({
      error: {
        code: status === 429 ? "rate_limited" : "mock_error",
        message,
        request_id: "e2e-request",
      },
    }),
  });
}
