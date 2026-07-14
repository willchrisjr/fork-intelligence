export type AnalysisMode = "explore" | "successor" | "innovation" | "compare";

export type AnalysisStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "partial"
  | "completed"
  | "failed"
  | "cancelled";

export type AnalysisStageStatus =
  "complete" | "active" | "queued" | "warning" | "failed";

export interface AnalysisStage {
  id: string;
  label: string;
  status: AnalysisStageStatus;
  progress?: number;
  detail?: string;
}

export interface AnalysisSummary {
  id: string;
  repository: string;
  rootRepositoryId?: string;
  status: AnalysisStatus;
  stage: string;
  progress: number;
  startedAt: string;
  updatedAt: string;
  discoveredForks: number;
  shortlistedForks: number;
  analyzedForks: number;
  pendingForks: number;
  rateLimitRemainingPercent?: number;
  rateLimitResetsAt?: string;
  isSampled: boolean;
  analysisVersion: string;
  analysisCommit?: string;
  stages: AnalysisStage[];
  warnings: string[];
}

export type Classification =
  | "mirror"
  | "contribution"
  | "experimental"
  | "specialized"
  | "compatibility_patch"
  | "maintained_continuation"
  | "independent_direction"
  | "unknown";

export type MaintenanceState =
  | "actively_maintained"
  | "maintained"
  | "low_activity"
  | "inactive"
  | "unknown";

export interface ScoreComponent {
  key: string;
  label: string;
  value: number | string | null;
  normalizedValue?: number;
  weight?: number;
  contribution?: number;
  missing?: boolean;
}

export interface EvidenceCounts {
  commits: number;
  patches: number;
  files: number;
  releases: number;
}

export interface ForkSummary {
  id: string;
  fullName: string;
  url: string;
  isFork: boolean;
  updatedAt: string;
  classification: Classification;
  maintenance: MaintenanceState;
  originalWorkPercent: number | null;
  activity30d: number | null;
  activity90d: number | null;
  uniqueCommits: number | null;
  confidence: number;
  dataCoverage: number;
  analysisDepth: "metadata" | "structural" | "deep";
  selected?: boolean;
  clusterId?: string;
  evidenceCounts: EvidenceCounts;
  scoreComponents: ScoreComponent[];
  missingData: string[];
}

export interface ForkPage {
  items: ForkSummary[];
  total: number;
  page: number;
  pageSize: number;
  availableClassifications: Classification[];
  partial: boolean;
  updatedAt: string;
  nextCursor?: string;
}

export interface EvidenceItem {
  id: string;
  type: "commit" | "patch" | "file" | "release" | "metadata" | "metric";
  title: string;
  summary: string;
  repository: string;
  sourceUrl?: string;
  reference?: string;
  confidence: number | null;
  provenance: "github" | "git" | "calculated" | "heuristic";
  retrievedAt: string;
}

export interface ForkDetail extends ForkSummary {
  description?: string;
  defaultBranch: string;
  headSha?: string;
  mergeBase?: string;
  ahead: number | null;
  behind: number | null;
  uniquePatches: number | null;
  classificationReasons: string[];
  evidence: EvidenceItem[];
  cluster?: { id: string; label: string; confidence: number };
}

export interface ComparisonRepository {
  id: string;
  role: "upstream" | "fork_a" | "fork_b";
  fullName: string;
  branch: string;
  headSha?: string;
  updatedAt: string;
}

export interface Comparison {
  id: string;
  analysisId: string;
  repositories: ComparisonRepository[];
  overlap: Array<{
    leftId: string;
    rightId: string;
    percent: number;
    count: number;
    basis: "patches" | "paths";
  }>;
  composition: Array<{ category: string; values: Record<string, number> }>;
  integration: Array<{
    label: string;
    status: "good" | "warning" | "unknown";
    detail: string;
  }>;
  evidence: EvidenceItem[];
  missingData: string[];
  updatedAt: string;
}

export interface GraphNode {
  id: string;
  label: string;
  classification: Classification;
  clusterId?: string;
  parentId?: string;
  confidence: number;
  originalWorkPercent: number | null;
  activity30d: number | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "lineage" | "similarity" | "patch_overlap";
  weight?: number;
}

export interface EvolutionGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  totalNodes: number;
  displayedNodes: number;
  bounded: boolean;
  updatedAt: string;
}

export interface DevelopmentCluster {
  id: string;
  label: string;
  summary: string;
  memberCount: number;
  memberIds: string[];
  members?: ForkSummary[];
  representativeEvidence: EvidenceItem[];
  sharedPaths: string[];
  sharedTechnologies: string[];
  confidence: number;
  method: string;
  labelMethod: "heuristic" | "ai_evidence_grounded";
}

export interface ApiErrorShape {
  code: string;
  message: string;
  requestId?: string;
  retryable: boolean;
  details?: Record<string, unknown>;
}

export interface ProgressEvent {
  id: string;
  type: "snapshot" | "stage" | "warning" | "partial" | "complete" | "error";
  occurredAt: string;
  analysis?: AnalysisSummary;
  message?: string;
}
