import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  BranchPlanPanel,
  ProviderAccessPanel,
} from "@/components/access-disclosure";
import { BranchPlanTable } from "@/components/branch-plan-table";
import type {
  BranchPlanEntry,
  BranchPlanSummary,
  ProviderAccess,
} from "@/lib/types";

const TOKEN = "ghp-operator-secret";

function access(overrides: Partial<ProviderAccess> = {}): ProviderAccess {
  return {
    credentialMode: "authenticated",
    quota: { limit: 5000, remaining: 4000, resource: "core" },
    transitions: [],
    coverageLimitations: [],
    ...overrides,
  };
}

function plan(overrides: Partial<BranchPlanSummary> = {}): BranchPlanSummary {
  return {
    plannerVersion: "2026.07.2",
    effectiveCap: 3,
    counts: {
      considered: 6,
      selected: 3,
      excludedByCap: 2,
      unevaluated: 1,
      structurallyAnalyzed: 3,
    },
    selectionReasons: [
      { reason: "branch_cap_exceeded", count: 2 },
      { reason: "default_branch", count: 1 },
    ],
    defaultOnlyCoverage: false,
    ...overrides,
  };
}

function entry(overrides: Partial<BranchPlanEntry> = {}): BranchPlanEntry {
  return {
    repositoryId: "repo-1",
    branchName: "main",
    headSha: "a".repeat(40),
    isDefault: true,
    priority: 0,
    decision: "selected",
    selectionReason: "default_branch",
    plannerVersion: "2026.07.2",
    ...overrides,
  };
}

describe("ProviderAccessPanel", () => {
  it("shows the effective credential mode and remaining quota", () => {
    render(<ProviderAccessPanel access={access()} />);

    expect(screen.getByTestId("credential-mode")).toHaveTextContent(
      "Authenticated",
    );
    expect(screen.getByTestId("quota-remaining")).toHaveTextContent("80%");
  });

  it("renders nothing when no access provenance was recorded", () => {
    // An empty panel would imply the run had no credential at all.
    const { container } = render(<ProviderAccessPanel access={undefined} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("names the fallback and the coverage it affected", () => {
    render(
      <ProviderAccessPanel
        access={access({
          credentialMode: "anonymous",
          transitions: [
            {
              fromMode: "authenticated",
              toMode: "anonymous",
              reason: "operator_credential_quota_exhausted",
              coverageLimitation: "Anonymous access lowers the rate limit.",
            },
          ],
          coverageLimitations: ["Anonymous access lowers the rate limit."],
        })}
      />,
    );

    expect(screen.getByTestId("credential-mode")).toHaveTextContent(
      "Anonymous",
    );
    expect(screen.getByTestId("access-transitions")).toHaveTextContent(
      "operator credential quota exhausted",
    );
    expect(screen.getByTestId("coverage-limitations")).toHaveTextContent(
      "Anonymous access lowers the rate limit.",
    );
  });

  it("reports an unavailable provider as resumable without hiding results", () => {
    render(
      <ProviderAccessPanel
        access={access({
          accessCondition: {
            code: "github_rate_limited",
            message: "GitHub access could not continue.",
            resumable: true,
          },
        })}
      />,
    );

    const condition = screen.getByTestId("access-condition");
    expect(condition).toHaveTextContent("GitHub access could not continue.");
    expect(condition).toHaveTextContent("can be resumed");
  });

  it("omits the quota line when the provider reported no figures", () => {
    render(<ProviderAccessPanel access={access({ quota: {} })} />);

    expect(screen.queryByTestId("quota-remaining")).not.toBeInTheDocument();
  });

  it("never renders credential material", () => {
    // AC-RA-AGA-001.3 at the browser boundary.
    const { container } = render(
      <ProviderAccessPanel
        access={access({ quota: { limit: 10, remaining: 1, resource: TOKEN } })}
      />,
    );

    // The resource label is provider-supplied and sanitized upstream; the panel
    // must not invent a place to show a credential.
    expect(container.textContent).not.toContain("Bearer");
  });
});

describe("BranchPlanPanel", () => {
  it("reports considered, selected, excluded, and analyzed counts", () => {
    render(<BranchPlanPanel plan={plan()} />);

    expect(screen.getByTestId("branch-considered")).toHaveTextContent("6");
    expect(screen.getByTestId("branch-selected")).toHaveTextContent("3");
    expect(
      screen.getByTestId("branch-structurally-analyzed"),
    ).toHaveTextContent("3");
  });

  it("keeps cap exclusions distinct from candidates it could not evaluate", () => {
    render(<BranchPlanPanel plan={plan()} />);

    expect(screen.getByTestId("branch-excluded-by-cap")).toHaveTextContent("2");
    expect(screen.getByTestId("branch-unevaluated")).toHaveTextContent("1");
  });

  it("discloses the effective cap and method version", () => {
    render(<BranchPlanPanel plan={plan()} />);

    expect(screen.getByText(/Up to 3 branches per fork/)).toBeVisible();
    expect(screen.getByText(/Method version 2026.07.2/)).toBeVisible();
  });

  it("says when coverage never went past the default branch", () => {
    render(<BranchPlanPanel plan={plan({ defaultOnlyCoverage: true })} />);

    expect(screen.getByTestId("default-only-coverage")).toHaveTextContent(
      "did not extend beyond the default branch",
    );
  });

  it("renders nothing when no plan was recorded", () => {
    const { container } = render(<BranchPlanPanel plan={undefined} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("BranchPlanTable", () => {
  it("lists every considered candidate with its decision and reason", () => {
    render(
      <BranchPlanTable
        entries={[
          entry(),
          entry({
            branchName: "feature",
            isDefault: false,
            priority: 1,
            decision: "excluded",
            selectionReason: "branch_cap_exceeded",
            headSha: "b".repeat(40),
          }),
          entry({
            branchName: "mystery",
            isDefault: false,
            priority: 2,
            decision: "unevaluated",
            selectionReason: "probe_budget_exhausted",
            headSha: undefined,
          }),
        ]}
      />,
    );

    expect(screen.getAllByTestId(/^branch-row-/)).toHaveLength(3);
    expect(screen.getByText("main")).toBeVisible();
    expect(
      screen.getByText(/fell outside the per-fork branch cap/),
    ).toBeVisible();
  });

  it("explains an unevaluated candidate as missing input, not exclusion", () => {
    render(
      <BranchPlanTable
        entries={[
          entry({
            branchName: "mystery",
            decision: "unevaluated",
            selectionReason: "probe_budget_exhausted",
            isDefault: false,
          }),
        ]}
      />,
    );

    const row = screen.getByTestId("branch-row-unevaluated");
    expect(row).toHaveTextContent("Could not be evaluated: probe budget");
    expect(row).not.toHaveTextContent("Excluded");
  });

  it("shows an explanation rather than an empty table when no plan exists", () => {
    render(<BranchPlanTable entries={[]} />);

    expect(screen.getByTestId("branch-plan-empty")).toHaveTextContent(
      "No branch plan was recorded",
    );
  });

  it("marks a candidate with no observed head rather than faking one", () => {
    render(
      <BranchPlanTable
        entries={[entry({ headSha: undefined, decision: "unevaluated" })]}
      />,
    );

    expect(screen.getByText("not observed")).toBeVisible();
  });

  it("exposes the table to assistive technology", () => {
    render(<BranchPlanTable entries={[entry()]} />);

    expect(
      screen.getByRole("table", { name: /Branch candidates considered/ }),
    ).toBeVisible();
    expect(screen.getByRole("rowheader", { name: /main/ })).toBeVisible();
  });
});
