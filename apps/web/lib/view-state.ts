import { z } from "zod";

const viewStateSchema = z.object({
  q: z.string().max(100).default(""),
  sort: z
    .enum([
      "maintained_successor",
      "unmerged_innovation",
      "maintenance",
      "original_development",
      "recent_activity",
      "adoption",
      "stars",
      "days_since_push",
      "unique_patches",
      "ahead",
      "behind",
      "name",
    ])
    .default("maintained_successor"),
  order: z.enum(["asc", "desc"]).default("desc"),
  classification: z.string().max(80).default(""),
  depth: z.enum(["", "metadata", "structural", "deep"]).default(""),
  selected: z.array(z.string().max(100)).max(3).default([]),
  evidence: z.string().max(100).default(""),
  graphMode: z.enum(["lineage", "cluster"]).default("lineage"),
  graphColor: z.enum(["classification", "cluster"]).default("classification"),
  graphSize: z
    .enum(["confidence", "original_work", "activity"])
    .default("confidence"),
  graphSearch: z.string().max(100).default(""),
  lowSignal: z.coerce.boolean().default(false),
  page: z.coerce.number().int().min(1).default(1),
  cursor: z.string().max(500).default(""),
});

export type WorkspaceViewState = z.infer<typeof viewStateSchema>;

export function parseViewState(params: URLSearchParams): WorkspaceViewState {
  const selected = params.getAll("selected");
  const parsed = viewStateSchema.safeParse({
    q: params.get("q") ?? undefined,
    sort: params.get("sort") ?? undefined,
    order: params.get("order") ?? undefined,
    classification: params.get("classification") ?? undefined,
    depth: params.get("depth") ?? undefined,
    selected,
    evidence: params.get("evidence") ?? undefined,
    graphMode: params.get("graphMode") ?? undefined,
    graphColor: params.get("graphColor") ?? undefined,
    graphSize: params.get("graphSize") ?? undefined,
    graphSearch: params.get("graphSearch") ?? undefined,
    lowSignal: params.get("lowSignal") === "1",
    page: params.get("page") ?? undefined,
    cursor: params.get("cursor") ?? undefined,
  });
  return parsed.success ? parsed.data : viewStateSchema.parse({});
}

export function serializeViewState(state: WorkspaceViewState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.sort !== "maintained_successor") params.set("sort", state.sort);
  if (state.order !== "desc") params.set("order", state.order);
  if (state.classification) params.set("classification", state.classification);
  if (state.depth) params.set("depth", state.depth);
  for (const id of state.selected) params.append("selected", id);
  if (state.evidence) params.set("evidence", state.evidence);
  if (state.graphMode !== "lineage") params.set("graphMode", state.graphMode);
  if (state.graphColor !== "classification")
    params.set("graphColor", state.graphColor);
  if (state.graphSize !== "confidence")
    params.set("graphSize", state.graphSize);
  if (state.graphSearch) params.set("graphSearch", state.graphSearch);
  if (state.lowSignal) params.set("lowSignal", "1");
  if (state.page !== 1) params.set("page", String(state.page));
  if (state.cursor) params.set("cursor", state.cursor);
  return params;
}
