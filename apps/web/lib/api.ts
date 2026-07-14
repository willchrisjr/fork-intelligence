import type {
  AnalysisMode,
  AnalysisStage,
  AnalysisStatus,
  AnalysisSummary,
  ApiErrorShape,
  Classification,
  Comparison,
  DevelopmentCluster,
  EvidenceItem,
  EvolutionGraph,
  ForkDetail,
  ForkPage,
  ForkSummary,
  MaintenanceState,
  ScoreComponent,
} from "./types";
import type { components as ContractComponents } from "@fork-intelligence/contracts";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1").replace(
  /\/$/,
  "",
);

type JsonRecord = Record<string, unknown>;
type ContractSchema<Name extends string> =
  Name extends keyof ContractComponents["schemas"]
    ? ContractComponents["schemas"][Name]
    : JsonRecord;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: ApiErrorShape,
  ) {
    super(payload.message);
    this.name = "ApiError";
  }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let payload: ApiErrorShape;
    try {
      const body = (await response.json()) as {
        error?: {
          code?: string;
          message?: string;
          details?: Record<string, unknown>;
          request_id?: string;
        };
        code?: string;
        detail?: string;
        title?: string;
        details?: Record<string, unknown>;
        request_id?: string;
      };
      payload = {
        code: body.code ?? body.error?.code ?? `http_${response.status}`,
        message:
          body.detail ??
          body.error?.message ??
          body.title ??
          response.statusText ??
          "Request failed",
        requestId: body.request_id ?? body.error?.request_id,
        retryable: response.status >= 500 || response.status === 429,
        details: body.details ?? body.error?.details,
      };
    } catch {
      payload = {
        code: `http_${response.status}`,
        message: response.statusText || "Request failed",
        retryable: response.status >= 500 || response.status === 429,
      };
    }
    throw new ApiError(response.status, payload);
  }
  return response.json();
}

const record = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
const array = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : [];
const string = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;
const number = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;
const nullableNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const boolean = (value: unknown): boolean => value === true;

const canonicalClassifications = new Set<Classification>([
  "mirror",
  "contribution",
  "experimental",
  "specialized",
  "compatibility_patch",
  "maintained_continuation",
  "independent_direction",
  "unknown",
]);
function classification(value: unknown): Classification {
  const key = string(value, "unknown") as Classification;
  return canonicalClassifications.has(key) ? key : "unknown";
}

function maintenance(
  metrics: JsonRecord,
  maintenanceScore?: JsonRecord,
): MaintenanceState {
  const raw = string(metrics.maintenance_state ?? metrics.maintenance);
  if (
    [
      "actively_maintained",
      "maintained",
      "low_activity",
      "inactive",
      "unknown",
    ].includes(raw)
  )
    return raw as MaintenanceState;
  if (!maintenanceScore || number(maintenanceScore.confidence) < 0.5)
    return "unknown";
  const value = number(maintenanceScore.value);
  if (value >= 75) return "actively_maintained";
  if (value >= 50) return "maintained";
  if (value >= 20) return "low_activity";
  return "inactive";
}

function mapStages(stage: string, progress: number): AnalysisStage[] {
  const definitions = [
    ["network_discovery", "Network discovery"],
    ["metadata_census", "Metadata census"],
    ["git_analysis", "Git analysis"],
    ["patch_equivalence", "Patch equivalence"],
    ["scoring", "Scoring"],
    ["clustering", "Clustering"],
  ] as const;
  let activeIndex = definitions.findIndex(
    ([id]) => stage.includes(id) || stage.replaceAll(".", "_").includes(id),
  );
  if (activeIndex < 0)
    activeIndex = Math.min(
      definitions.length - 1,
      Math.floor((progress / 100) * definitions.length),
    );
  return definitions.map(([id, label], index) => ({
    id,
    label,
    status:
      progress >= 100 || index < activeIndex
        ? "complete"
        : index === activeIndex
          ? "active"
          : "queued",
    progress: index === activeIndex ? Math.round(progress) : undefined,
  }));
}

function mapAnalysis(
  value: ContractSchema<"AnalysisRead"> | unknown,
): AnalysisSummary {
  const raw = record(value);
  const sampling = record(raw.sampling);
  const quota = record(raw.quota_snapshot);
  const counts = record(sampling.counts);
  const rawProgress = number(raw.progress);
  const progress = rawProgress <= 1 ? rawProgress * 100 : rawProgress;
  const warnings = array(raw.warnings)
    .map((item) => string(record(item).message, string(item)))
    .filter(Boolean);
  const status = string(raw.status, "queued") as AnalysisStatus;
  const updatedAt = string(raw.updated_at, new Date(0).toISOString());
  return {
    id: string(raw.id),
    repository: string(raw.requested_identifier, "Unknown repository"),
    rootRepositoryId: string(raw.root_repository_id) || undefined,
    status,
    stage: string(raw.stage, "queued").replaceAll("_", " "),
    progress: Math.round(progress),
    startedAt: string(raw.started_at, string(raw.created_at, updatedAt)),
    updatedAt,
    discoveredForks: number(
      counts.discovered ??
        sampling.discovered_forks ??
        sampling.accessible_forks,
    ),
    shortlistedForks: number(
      counts.shortlisted ??
        sampling.shortlisted_forks ??
        sampling.deep_repositories_selected,
    ),
    analyzedForks: number(
      counts.analyzed ??
        sampling.analyzed_forks ??
        sampling.deep_repositories_analyzed,
    ),
    pendingForks: number(counts.pending ?? sampling.pending_forks),
    rateLimitRemainingPercent: (() => {
      const percentage =
        nullableNumber(quota.remaining_percent) ??
        (number(quota.limit) > 0
          ? (number(quota.remaining) / number(quota.limit)) * 100
          : undefined);
      return percentage == null ? undefined : Math.round(percentage * 10) / 10;
    })(),
    rateLimitResetsAt: string(quota.resets_at) || undefined,
    isSampled: boolean(
      sampling.is_sampled ?? sampling.sampled ?? sampling.forks_capped,
    ),
    analysisVersion: string(raw.analysis_version, "unknown"),
    analysisCommit:
      string(record(raw.configuration).analysis_commit) || undefined,
    stages: mapStages(string(raw.stage), progress),
    warnings,
  };
}

function mapScoreComponents(scores: unknown): ScoreComponent[] {
  return array(scores).map((item, index) => {
    const score = record(item);
    return {
      key: string(score.dimension ?? score.key, `score-${index}`),
      label: string(score.label ?? score.dimension, "Score"),
      value: (score.raw_value ?? score.value ?? null) as number | string | null,
      normalizedValue: nullableNumber(score.normalized_value) ?? undefined,
      weight: nullableNumber(score.weight) ?? undefined,
      contribution: nullableNumber(score.contribution) ?? undefined,
      missing: boolean(score.missing),
    };
  });
}

function mapFork(value: unknown): ForkSummary {
  const raw = record(value);
  const metrics = record(raw.metrics);
  const classRaw = record(raw.classification);
  const metadata = record(raw.metadata);
  const scoresByDimension = new Map(
    array(raw.scores).map((item) => {
      const score = record(item);
      return [string(score.dimension), score] as const;
    }),
  );
  const originalDevelopment = nullableNumber(
    scoresByDimension.get("original_development")?.value,
  );
  return {
    id: string(raw.id),
    fullName: `${string(raw.owner, "unknown")}/${string(raw.name, "repository")}`,
    url: string(raw.html_url),
    isFork: boolean(raw.is_fork),
    updatedAt: string(
      metadata.updated_at ?? metadata.pushed_at,
      new Date(0).toISOString(),
    ),
    classification: classification(classRaw.label),
    maintenance: maintenance(metrics, scoresByDimension.get("maintenance")),
    originalWorkPercent:
      nullableNumber(metrics.original_work_percent) ??
      (originalDevelopment == null
        ? null
        : originalDevelopment <= 1
          ? originalDevelopment * 100
          : originalDevelopment),
    activity30d: nullableNumber(metrics.activity_30d ?? metrics.commits_30d),
    activity90d: nullableNumber(metrics.activity_90d ?? metrics.commits_90d),
    uniqueCommits: nullableNumber(metrics.unique_commits),
    confidence: number(classRaw.confidence ?? metrics.confidence),
    dataCoverage: (() => {
      const value = number(
        metrics.data_coverage,
        string(raw.depth) === "deep"
          ? 1
          : string(raw.depth) === "structural"
            ? 0.7
            : 0.35,
      );
      return value <= 1 ? value * 100 : value;
    })(),
    analysisDepth: (["metadata", "structural", "deep"].includes(
      string(raw.depth),
    )
      ? string(raw.depth)
      : "metadata") as ForkSummary["analysisDepth"],
    clusterId: string(metrics.cluster_id) || undefined,
    evidenceCounts: {
      commits: number(metrics.evidence_commits ?? metrics.unique_commits),
      patches: number(metrics.evidence_patches ?? metrics.unique_patches),
      files: number(metrics.evidence_files ?? metrics.changed_files),
      releases: number(metrics.evidence_releases ?? metadata.releases_count),
    },
    scoreComponents: mapScoreComponents(raw.scores),
    missingData: array(metrics.missing_data).map(String),
  };
}

function mapEvidence(value: unknown, repository: string): EvidenceItem {
  const raw = record(value);
  const payload = record(raw.payload);
  const provenance = record(raw.provenance);
  const source = string(raw.source, "calculated");
  const ahead = nullableNumber(payload.ahead);
  const behind = nullableNumber(payload.behind);
  const uniqueCommits = nullableNumber(payload.unique_commits);
  const patchIds = array(payload.patch_ids);
  const changedFiles = array(payload.changed_files);
  const summary =
    ahead != null || behind != null
      ? `${ahead ?? "Unknown"} commits ahead and ${behind ?? "unknown"} behind; ${uniqueCommits ?? "unknown"} unique commits, ${patchIds.length} deterministic patch fingerprints, and ${changedFiles.length} changed files. Merge base ${string(payload.merge_base, "unavailable")}.`
      : string(
          raw.summary ?? raw.description,
          "Structured evidence is available from the analysis service.",
        );
  return {
    id: string(raw.id ?? raw.evidence_id),
    type: ([
      "commit",
      "patch",
      "file",
      "release",
      "metadata",
      "metric",
    ].includes(string(raw.type))
      ? string(raw.type)
      : "metric") as EvidenceItem["type"],
    title: string(
      raw.title,
      string(raw.type) === "calculated_metric"
        ? "Git history and patch analysis"
        : "Calculated evidence",
    ),
    summary,
    repository,
    sourceUrl: string(raw.source_url) || undefined,
    reference: string(raw.reference ?? raw.commit_sha) || undefined,
    confidence: nullableNumber(raw.confidence),
    provenance: (source === "git"
      ? "git"
      : source === "github"
        ? "github"
        : provenance.method
          ? "calculated"
          : "calculated") as EvidenceItem["provenance"],
    retrievedAt: string(
      raw.retrieved_at ?? provenance.retrieved_at,
      new Date(0).toISOString(),
    ),
  };
}

function mapForkDetail(value: unknown): ForkDetail {
  const fork = mapFork(value);
  const raw = record(value);
  const metrics = record(raw.metrics);
  const classRaw = record(raw.classification);
  const metadata = record(raw.metadata);
  return {
    ...fork,
    description: string(metadata.description) || undefined,
    defaultBranch: string(raw.default_branch, "unknown"),
    headSha: string(metrics.head_sha) || undefined,
    mergeBase: string(metrics.merge_base) || undefined,
    ahead: nullableNumber(metrics.ahead),
    behind: nullableNumber(metrics.behind),
    uniquePatches: nullableNumber(metrics.unique_patches),
    classificationReasons: array(classRaw.reasons).map(String),
    evidence: array(raw.evidence).map((item) =>
      mapEvidence(item, fork.fullName),
    ),
    cluster: string(metrics.cluster_id)
      ? {
          id: string(metrics.cluster_id),
          label: string(metrics.cluster_label, "Development direction"),
          confidence: number(metrics.cluster_confidence),
        }
      : undefined,
  };
}

function mapForkPage(value: unknown): ForkPage {
  const raw = record(value);
  const items = array(raw.items).map(mapFork);
  return {
    items,
    total: number(raw.total, items.length),
    page: number(raw.page, 1),
    pageSize: number(raw.per_page ?? raw.limit, items.length || 25),
    availableClassifications: [...canonicalClassifications],
    partial: boolean(raw.partial),
    updatedAt: string(raw.updated_at, new Date().toISOString()),
    nextCursor: string(raw.next_cursor) || undefined,
  };
}

function mapComparison(value: unknown): Comparison {
  const raw = record(value);
  const result = record(raw.result);
  const repositoryItems = array(result.repositories).length
    ? array(result.repositories)
    : array(raw.repository_ids).map((id) => ({
        id,
        full_name: `Repository ${String(id).slice(0, 8)}`,
      }));
  const repositories = repositoryItems.map((item, index) => {
    const repository = record(item);
    return {
      id: string(
        repository.id ??
          repository.repository_id ??
          array(raw.repository_ids)[index],
      ),
      role: (index === 0 ? "upstream" : index === 1 ? "fork_a" : "fork_b") as
        "upstream" | "fork_a" | "fork_b",
      fullName: string(
        repository.full_name ?? repository.name,
        `Repository ${index + 1}`,
      ),
      branch: string(repository.branch ?? repository.default_branch, "default"),
      headSha: string(repository.head_sha) || undefined,
      updatedAt: string(
        repository.updated_at,
        string(raw.updated_at, new Date(0).toISOString()),
      ),
    };
  });
  return {
    id: string(raw.id),
    analysisId: string(raw.analysis_id),
    repositories,
    overlap: (array(result.overlap).length
      ? array(result.overlap)
      : array(result.pairs)
    ).map((item) => {
      const overlap = record(item);
      const isPair = "path_overlap" in overlap;
      return {
        leftId: string(overlap.left_id ?? overlap.left_repository_id),
        rightId: string(overlap.right_id ?? overlap.right_repository_id),
        percent: isPair
          ? number(overlap.path_overlap) * 100
          : number(overlap.percent),
        count: isPair
          ? array(overlap.shared_changed_paths).length
          : number(overlap.patches),
        basis: isPair ? ("paths" as const) : ("patches" as const),
      };
    }),
    composition: (() => {
      const rows = array(result.composition).map(record);
      const categories = new Set(
        rows.flatMap((row) => Object.keys(record(row.categories))),
      );
      const totals = new Map(
        rows.map((row) => [
          string(row.repository_id),
          Object.values(record(row.categories)).reduce<number>(
            (total, value) => total + number(value),
            0,
          ),
        ]),
      );
      return [...categories]
        .map((category) => ({
          category,
          values: Object.fromEntries(
            rows.map((row) => {
              const repositoryId = string(row.repository_id);
              const total = totals.get(repositoryId) ?? 0;
              const value = number(record(row.categories)[category]);
              return [
                repositoryId,
                total ? Math.round((value / total) * 100) : 0,
              ];
            }),
          ),
        }))
        .filter((category) =>
          Object.values(category.values).some((value) => value > 0),
        );
    })(),
    integration: array(result.integration).map((item) => {
      const integration = record(item);
      const estimate = string(integration.status ?? integration.estimate);
      return {
        label: string(integration.label, "Integration complexity"),
        status: (["lower", "bounded", "good"].includes(estimate)
          ? "good"
          : ["moderate", "high", "warning"].includes(estimate)
            ? "warning"
            : "unknown") as "good" | "warning" | "unknown",
        detail: string(
          integration.detail ?? integration.disclosure,
          estimate || "Unknown",
        ),
      };
    }),
    evidence: array(result.evidence).map((item) =>
      mapEvidence(item, "comparison"),
    ),
    missingData: array(result.missing_data).map(String),
    updatedAt: string(raw.updated_at, new Date(0).toISOString()),
  };
}

export const api = {
  async createAnalysis(
    repository: string,
    mode: AnalysisMode,
    signal?: AbortSignal,
  ) {
    return mapAnalysis(
      await request("/analyses", {
        method: "POST",
        body: JSON.stringify({ repository, mode }),
        signal,
      }),
    );
  },
  async getAnalysis(id: string, signal?: AbortSignal) {
    return mapAnalysis(
      await request(`/analyses/${encodeURIComponent(id)}`, { signal }),
    );
  },
  async getAnalysisOverview(id: string, signal?: AbortSignal) {
    const raw = record(
      await request(`/analyses/${encodeURIComponent(id)}/overview`, { signal }),
    );
    const summary = mapAnalysis(raw.analysis);
    const counts = record(raw.counts);
    const coverage = record(raw.data_coverage);
    const discovered = number(counts.forks, summary.discoveredForks);
    const analyzed = number(coverage.structural, summary.analyzedForks);
    return {
      ...summary,
      discoveredForks: discovered,
      shortlistedForks: number(counts.shortlisted, summary.shortlistedForks),
      analyzedForks: analyzed,
      pendingForks: Math.max(0, discovered - analyzed),
    };
  },
  async getForks(
    id: string,
    params: {
      cursor?: string;
      pageSize?: number;
      q?: string;
      sort?: string;
      order?: string;
      classification?: string;
      depth?: string;
    },
    signal?: AbortSignal,
  ) {
    const search = new URLSearchParams();
    if (params.cursor) search.set("cursor", params.cursor);
    if (params.pageSize) search.set("limit", String(params.pageSize));
    if (params.q) search.set("search", params.q);
    if (params.sort) search.set("sort", params.sort);
    if (params.order) search.set("order", params.order);
    if (params.classification)
      search.set("classification", params.classification);
    if (params.depth) search.set("depth", params.depth);
    return mapForkPage(
      await request(`/analyses/${encodeURIComponent(id)}/forks?${search}`, {
        signal,
      }),
    );
  },
  async getUpstreamId(id: string, signal?: AbortSignal) {
    let cursor = "";
    for (let pageIndex = 0; pageIndex < 20; pageIndex += 1) {
      const page = await this.getForks(
        id,
        { cursor, pageSize: 100, sort: "name", order: "asc" },
        signal,
      );
      const upstream = page.items.find((fork) => !fork.isFork);
      if (upstream) return upstream.id;
      if (!page.nextCursor) break;
      cursor = page.nextCursor;
    }
    throw new ApiError(422, {
      code: "upstream_unavailable",
      message:
        "The network root is not available in the accessible fork census.",
      retryable: false,
    });
  },
  async getFork(id: string, repositoryId: string, signal?: AbortSignal) {
    return mapForkDetail(
      await request(
        `/analyses/${encodeURIComponent(id)}/forks/${encodeURIComponent(repositoryId)}`,
        { signal },
      ),
    );
  },
  async getEvolution(
    id: string,
    params: URLSearchParams,
    signal?: AbortSignal,
  ) {
    const raw = record(
      await request(`/analyses/${encodeURIComponent(id)}/evolution?${params}`, {
        signal,
      }),
    );
    const sampling = record(raw.sampling);
    const nodes = array(raw.nodes).map((item) => {
      const node = record(item);
      const metrics = record(node.metrics);
      return {
        id: string(node.repository_id),
        label: string(node.full_name, "Unknown repository"),
        classification: classification(node.classification),
        clusterId: string(node.cluster_id) || undefined,
        confidence: number(
          metrics.confidence ?? metrics.classification_confidence,
        ),
        originalWorkPercent: nullableNumber(
          metrics.original_work_percent ?? metrics.original_development,
        ),
        activity30d: nullableNumber(
          metrics.activity_30d ?? metrics.commits_30d,
        ),
      };
    });
    return {
      nodes,
      edges: array(raw.edges).map((item, index) => {
        const edge = record(item);
        return {
          id: `edge-${index}-${string(edge.source_repository_id)}-${string(edge.target_repository_id)}`,
          source: string(edge.source_repository_id),
          target: string(edge.target_repository_id),
          kind:
            string(edge.relationship) === "fork"
              ? ("lineage" as const)
              : ("similarity" as const),
        };
      }),
      totalNodes: number(
        sampling.forks_discovered ?? sampling.repositories_discovered,
        nodes.length,
      ),
      displayedNodes: nodes.length,
      bounded:
        boolean(sampling.forks_capped) ||
        number(sampling.forks_discovered, nodes.length) > nodes.length,
      updatedAt: new Date().toISOString(),
    } satisfies EvolutionGraph;
  },
  async getClusters(id: string, signal?: AbortSignal) {
    const response = await request(
      `/analyses/${encodeURIComponent(id)}/clusters`,
      { signal },
    );
    const items = Array.isArray(response)
      ? response
      : array(record(response).items);
    return {
      items: items.map((item) => {
        const cluster = record(item);
        const memberIds = array(cluster.member_repository_ids).map(String);
        return {
          id: string(cluster.id),
          label: string(cluster.label, "Unlabeled direction"),
          summary: string(cluster.summary),
          memberCount: memberIds.length,
          memberIds,
          representativeEvidence: [],
          sharedPaths: array(cluster.shared_paths).map(String),
          sharedTechnologies: array(cluster.shared_technologies).map(String),
          confidence: number(cluster.confidence),
          method: string(cluster.algorithm, "unknown"),
          labelMethod:
            string(cluster.labeling_method) === "ai_evidence_grounded"
              ? "ai_evidence_grounded"
              : "heuristic",
        } satisfies DevelopmentCluster;
      }),
    };
  },
  async createComparison(
    id: string,
    repositoryIds: string[],
    signal?: AbortSignal,
  ) {
    return mapComparison(
      await request(`/analyses/${encodeURIComponent(id)}/comparisons`, {
        method: "POST",
        body: JSON.stringify({ repository_ids: repositoryIds }),
        signal,
      }),
    );
  },
  async getComparison(comparisonId: string, signal?: AbortSignal) {
    return mapComparison(
      await request(`/comparisons/${encodeURIComponent(comparisonId)}`, {
        signal,
      }),
    );
  },
  async cancelAnalysis(id: string, signal?: AbortSignal) {
    return mapAnalysis(
      await request(`/analyses/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
        signal,
      }),
    );
  },
  async resumeAnalysis(id: string, signal?: AbortSignal) {
    return mapAnalysis(
      await request(`/analyses/${encodeURIComponent(id)}/resume`, {
        method: "POST",
        signal,
      }),
    );
  },
  exportUrl(id: string, format: "json" | "csv" | "markdown") {
    return `${API_BASE}/analyses/${encodeURIComponent(id)}/exports/${format}`;
  },
  progressUrl(id: string) {
    return `${API_BASE}/analyses/${encodeURIComponent(id)}/events`;
  },
};
