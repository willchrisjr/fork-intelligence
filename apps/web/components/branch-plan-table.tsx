import type { BranchDecision, BranchPlanEntry } from "@/lib/types";

const DECISION_LABEL: Record<BranchDecision, string> = {
  selected: "Selected",
  excluded: "Excluded",
  unevaluated: "Not evaluated",
};

/**
 * Explains one decision in the investigator's terms.
 *
 * An unevaluated candidate names the missing input rather than being given a
 * definitive exclusion reason, so a gap in data never reads as a judgement
 * about the branch.
 */
function explain(entry: BranchPlanEntry): string {
  const reason = entry.selectionReason?.replaceAll("_", " ");
  if (entry.decision === "unevaluated") {
    return reason
      ? `Could not be evaluated: ${reason}`
      : "Could not be evaluated; the required input was unavailable.";
  }
  if (entry.decision === "excluded") {
    return entry.selectionReason === "branch_cap_exceeded"
      ? `Ranked ${entry.priority} and fell outside the per-fork branch cap`
      : (reason ?? "Excluded");
  }
  return reason ?? "Selected";
}

/**
 * Every branch candidate considered for one repository, in plan order.
 *
 * Excluded and unevaluated candidates are shown alongside selected ones: the
 * point of the disclosure is to let a researcher tell repository behavior apart
 * from the product's own sampling.
 */
export function BranchPlanTable({
  entries,
}: {
  entries: BranchPlanEntry[];
}): React.ReactElement {
  if (entries.length === 0) {
    return (
      <section aria-labelledby="branch-plan-table-heading">
        <h3 id="branch-plan-table-heading" className="text-sm font-semibold">
          Branch plan
        </h3>
        <p
          className="mt-2 text-sm text-[var(--muted-foreground)]"
          data-testid="branch-plan-empty"
        >
          No branch plan was recorded for this repository. This analysis may
          predate branch planning, or it stopped before the planning stage.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="branch-plan-table-heading">
      <h3 id="branch-plan-table-heading" className="text-sm font-semibold">
        Branch plan
      </h3>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        {entries.length} candidate{entries.length === 1 ? "" : "s"} considered,
        in the order the planner ranked them.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">
            Branch candidates considered for this repository, with the decision
            and reason for each
          </caption>
          <thead>
            <tr className="border-b border-[var(--border)]">
              <th scope="col" className="py-2 pr-3 font-medium">
                Branch
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Decision
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Why
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Observed head
              </th>
            </tr>
          </thead>
          <tbody data-testid="branch-plan-rows">
            {entries.map((entry) => (
              <tr
                key={`${entry.plannerVersion}-${entry.branchName}`}
                className="border-b border-[var(--border)] last:border-0"
                data-testid={`branch-row-${entry.decision}`}
              >
                <th scope="row" className="py-2 pr-3 font-normal">
                  <code>{entry.branchName}</code>
                  {entry.isDefault ? (
                    <span className="ml-2 rounded border border-[var(--border)] px-1 text-xs">
                      default
                    </span>
                  ) : null}
                </th>
                <td className="py-2 pr-3">{DECISION_LABEL[entry.decision]}</td>
                <td className="py-2 pr-3 text-[var(--muted-foreground)]">
                  {explain(entry)}
                </td>
                <td className="py-2 pr-3">
                  {entry.headSha ? (
                    <code title={entry.headSha}>
                      {entry.headSha.slice(0, 10)}
                    </code>
                  ) : (
                    <span className="text-[var(--muted-foreground)]">
                      not observed
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
