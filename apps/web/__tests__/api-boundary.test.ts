import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("API boundary mapping", () => {
  it("maps snake_case analysis read models into stable UI models", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "analysis-1",
            requested_identifier: "owner/project",
            requested_repository_id: "root-1",
            root_repository_id: "root-1",
            status: "running",
            stage: "metadata_census",
            progress: 0.424,
            sampling: {
              sampled: true,
              counts: {
                discovered: 120,
                shortlisted: 18,
                analyzed: 9,
                pending: 111,
              },
            },
            quota_snapshot: { remaining: 51, limit: 100 },
            warnings: [{ code: "quota", message: "Rate limit is approaching" }],
            analysis_version: "2026.07",
            created_at: "2026-07-13T20:00:00Z",
            updated_at: "2026-07-13T20:05:00Z",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );

    const result = await api.getAnalysis("analysis-1");
    expect(result.repository).toBe("owner/project");
    expect(result.rootRepositoryId).toBe("root-1");
    expect(result.progress).toBe(42);
    expect(result.rateLimitRemainingPercent).toBe(51);
    expect(result.discoveredForks).toBe(120);
    expect(result.warnings).toEqual(["Rate limit is approaching"]);
    expect(result.stages.some((stage) => stage.status === "active")).toBe(true);
  });

  it("maps canonical problem+json errors without leaking unknown fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "https://fork-intelligence.local/problems/rate-limited",
            title: "Rate limited",
            status: 429,
            detail: "Quota exhausted",
            code: "rate_limited",
            details: { resets_at: "later" },
            request_id: "req-1",
          }),
          {
            status: 429,
            headers: { "content-type": "application/problem+json" },
          },
        ),
      ),
    );
    await expect(api.getAnalysis("analysis-1")).rejects.toMatchObject({
      status: 429,
      payload: {
        code: "rate_limited",
        message: "Quota exhausted",
        requestId: "req-1",
        retryable: true,
      },
    } satisfies Partial<ApiError>);
  });

  it("uses cursor pagination and maps repository evidence fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              id: "fork-1",
              owner: "team",
              name: "project",
              html_url: "https://github.com/team/project",
              default_branch: "main",
              depth: "structural",
              metadata: { updated_at: "2026-07-12T00:00:00Z" },
              metrics: {
                unique_commits: 18,
                commits_30d: 4,
                original_work_percent: 31.5,
                data_coverage: 78,
              },
              classification: {
                label: "specialized",
                confidence: 0.82,
                reasons: ["Distinct source changes"],
              },
              scores: [],
            },
          ],
          total: 44,
          limit: 25,
          next_cursor: "next-opaque",
          partial: true,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const page = await api.getForks("analysis-1", {
      cursor: "current",
      pageSize: 25,
    });
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("cursor=current");
    expect(page.nextCursor).toBe("next-opaque");
    expect(page.items[0]).toMatchObject({
      fullName: "team/project",
      classification: "specialized",
      maintenance: "unknown",
      uniqueCommits: 18,
      analysisDepth: "structural",
    });
  });

  it("uses fork-only overview counts and rounds quota percentages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            analysis: {
              id: "analysis-1",
              requested_identifier: "owner/project",
              status: "completed",
              stage: "complete",
              progress: 1,
              sampling: { accessible_forks: 3 },
              quota_snapshot: { remaining: 44, limit: 60 },
              warnings: [],
              analysis_version: "2026.07",
              created_at: "2026-07-13T20:00:00Z",
              updated_at: "2026-07-13T20:05:00Z",
            },
            counts: { repositories: 4, forks: 3, shortlisted: 2 },
            data_coverage: { structural: 2 },
          }),
          { status: 200 },
        ),
      ),
    );

    const overview = await api.getAnalysisOverview("analysis-1");
    expect(overview.discoveredForks).toBe(3);
    expect(overview.pendingForks).toBe(1);
    expect(overview.rateLimitRemainingPercent).toBe(73.3);
  });

  it("maps finalized evolution node and edge identifiers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            nodes: [
              {
                repository_id: "root-1",
                full_name: "owner/project",
                is_root: true,
                classification: "maintained_continuation",
                cluster_id: "cluster-1",
                metrics: { confidence: 0.91, original_work_percent: 22 },
              },
            ],
            edges: [
              {
                source_repository_id: "root-1",
                target_repository_id: "fork-1",
                relationship: "fork",
              },
            ],
            sampling: { forks_capped: true, forks_discovered: 800 },
            provenance: { analysis_version: "2026.07" },
          }),
          { status: 200 },
        ),
      ),
    );
    const graph = await api.getEvolution("analysis-1", new URLSearchParams());
    expect(graph.nodes[0]).toMatchObject({
      id: "root-1",
      label: "owner/project",
      classification: "maintained_continuation",
    });
    expect(graph.edges[0]).toMatchObject({
      source: "root-1",
      target: "fork-1",
      kind: "lineage",
    });
    expect(graph.bounded).toBe(true);
  });

  it("derives score and calculated Git evidence display fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "fork-1",
            owner: "team",
            name: "project",
            html_url: "https://github.com/team/project",
            default_branch: "main",
            is_fork: true,
            depth: "structural",
            metadata: {},
            metrics: { ahead: 4, behind: 1, unique_commits: 4 },
            classification: {
              label: "specialized",
              confidence: 0.8,
              reasons: ["Distinct paths"],
            },
            scores: [{ dimension: "original_development", value: 0.63 }],
            evidence: [
              {
                id: "evidence-1",
                type: "calculated_metric",
                source: "git",
                source_url:
                  "https://github.com/team/project/compare/base...head",
                payload: {
                  ahead: 4,
                  behind: 1,
                  unique_commits: 4,
                  patch_ids: ["p1", "p2"],
                  changed_files: ["src/a.ts"],
                  merge_base: "abc123",
                },
                provenance: { method: "native-git" },
              },
            ],
          }),
          { status: 200 },
        ),
      ),
    );
    const detail = await api.getFork("analysis-1", "fork-1");
    expect(detail.originalWorkPercent).toBe(63);
    expect(detail.evidence[0]).toMatchObject({
      title: "Git history and patch analysis",
      provenance: "git",
    });
    expect(detail.evidence[0]?.summary).toContain(
      "4 commits ahead and 1 behind",
    );
  });
});
