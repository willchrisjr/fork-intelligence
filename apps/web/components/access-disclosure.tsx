import type { BranchPlanSummary, ProviderAccess } from "@/lib/types";

const MODE_LABEL: Record<string, string> = {
  authenticated: "Authenticated",
  anonymous: "Anonymous",
};

const MODE_DESCRIPTION: Record<string, string> = {
  authenticated:
    "This analysis used the operator's read-only GitHub credential, giving it the full authenticated rate limit.",
  anonymous:
    "This analysis used unauthenticated GitHub access, which applies a lower rate limit and can reduce fork and branch coverage.",
};

function quotaPercent(access: ProviderAccess): number | undefined {
  const { limit, remaining } = access.quota;
  if (limit == null || remaining == null || limit <= 0) {
    return undefined;
  }
  return Math.round((remaining / limit) * 1000) / 10;
}

/**
 * Effective provider access and capacity for an analysis.
 *
 * Renders nothing when the analysis carries no access provenance, rather than
 * an empty panel that would imply the run had none. The operator credential is
 * never part of this data — only which mode was in effect.
 */
export function ProviderAccessPanel({
  access,
}: {
  access?: ProviderAccess;
}): React.ReactElement | null {
  if (!access) {
    return null;
  }
  const percent = quotaPercent(access);
  const mode = access.credentialMode;
  return (
    <section
      aria-labelledby="provider-access-heading"
      className="rounded-lg border border-[var(--border)] p-4"
    >
      <h3 id="provider-access-heading" className="text-sm font-semibold">
        Provider access
      </h3>

      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span
          className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs font-medium"
          data-testid="credential-mode"
          data-mode={mode}
        >
          {MODE_LABEL[mode] ?? mode}
        </span>
        <span className="text-[var(--muted-foreground)]">
          {MODE_DESCRIPTION[mode] ?? "Provider access mode is unknown."}
        </span>
      </p>

      {percent != null ? (
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          Provider quota remaining:{" "}
          <span data-testid="quota-remaining">{percent}%</span>
          {access.quota.remaining != null && access.quota.limit != null ? (
            <>
              {" "}
              ({access.quota.remaining} of {access.quota.limit}
              {access.quota.resource ? ` ${access.quota.resource}` : ""})
            </>
          ) : null}
        </p>
      ) : null}

      {access.accessCondition ? (
        <p
          className="mt-3 rounded border border-[var(--border)] p-2 text-sm"
          role="status"
          data-testid="access-condition"
        >
          <strong>Provider access could not continue.</strong>{" "}
          {access.accessCondition.message ?? access.accessCondition.code}
          {access.accessCondition.resumable
            ? " Partial results below are preserved and this analysis can be resumed."
            : null}
        </p>
      ) : null}

      {access.transitions.length > 0 ? (
        <div className="mt-3">
          <h4 className="text-xs font-semibold tracking-wide text-[var(--muted-foreground)] uppercase">
            Access changes during this analysis
          </h4>
          <ul
            className="mt-1 space-y-1 text-sm"
            data-testid="access-transitions"
          >
            {access.transitions.map((transition, index) => (
              <li key={`${transition.reason}-${index}`}>
                {MODE_LABEL[transition.fromMode] ?? transition.fromMode} →{" "}
                {MODE_LABEL[transition.toMode] ?? transition.toMode}:{" "}
                <span className="text-[var(--muted-foreground)]">
                  {transition.reason.replaceAll("_", " ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {access.coverageLimitations.length > 0 ? (
        <div className="mt-3">
          <h4 className="text-xs font-semibold tracking-wide text-[var(--muted-foreground)] uppercase">
            Affected coverage
          </h4>
          <ul
            className="mt-1 list-disc space-y-1 pl-5 text-sm text-[var(--muted-foreground)]"
            data-testid="coverage-limitations"
          >
            {access.coverageLimitations.map((limitation) => (
              <li key={limitation}>{limitation.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Branch-plan scope and structural coverage for an analysis.
 *
 * Cap exclusions and unevaluable candidates are presented as separate figures:
 * one is a sampling choice the product made, the other is data it could not
 * obtain, and conflating them would misrepresent coverage.
 */
export function BranchPlanPanel({
  plan,
}: {
  plan?: BranchPlanSummary;
}): React.ReactElement | null {
  if (!plan) {
    return null;
  }
  const { counts } = plan;
  const figures = [
    { label: "Considered", value: counts.considered, testId: "considered" },
    { label: "Selected", value: counts.selected, testId: "selected" },
    {
      label: "Excluded by cap",
      value: counts.excludedByCap,
      testId: "excluded-by-cap",
    },
    {
      label: "Could not evaluate",
      value: counts.unevaluated,
      testId: "unevaluated",
    },
    {
      label: "Structurally analyzed",
      value: counts.structurallyAnalyzed,
      testId: "structurally-analyzed",
    },
  ];
  return (
    <section
      aria-labelledby="branch-plan-heading"
      className="rounded-lg border border-[var(--border)] p-4"
    >
      <h3 id="branch-plan-heading" className="text-sm font-semibold">
        Branch coverage
      </h3>

      <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {figures.map((figure) => (
          <div key={figure.testId}>
            <dt className="text-xs text-[var(--muted-foreground)]">
              {figure.label}
            </dt>
            <dd
              className="text-lg font-semibold tabular-nums"
              data-testid={`branch-${figure.testId}`}
            >
              {figure.value}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-sm text-[var(--muted-foreground)]">
        {plan.effectiveCap != null
          ? `Up to ${plan.effectiveCap} branch${plan.effectiveCap === 1 ? "" : "es"} per fork.`
          : "Branch cap not recorded."}
        {plan.plannerVersion ? ` Method version ${plan.plannerVersion}.` : ""}
      </p>

      {plan.defaultOnlyCoverage ? (
        <p
          className="mt-2 rounded border border-[var(--border)] p-2 text-sm"
          role="note"
          data-testid="default-only-coverage"
        >
          Structural coverage did not extend beyond the default branch.
        </p>
      ) : null}

      {plan.selectionReasons.length > 0 ? (
        <div className="mt-3">
          <h4 className="text-xs font-semibold tracking-wide text-[var(--muted-foreground)] uppercase">
            Why branches were selected or excluded
          </h4>
          <ul
            className="mt-1 space-y-1 text-sm"
            data-testid="selection-reasons"
          >
            {plan.selectionReasons.map((item) => (
              <li key={item.reason}>
                {item.reason.replaceAll("_", " ")}:{" "}
                <span className="tabular-nums">{item.count}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
