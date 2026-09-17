import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceInspector } from "@/components/evidence-inspector";
import { StarGrowthPanel } from "@/components/star-growth-panel";
import type { ForkDetail, StarGrowth } from "@/lib/types";

const growth: StarGrowth = {
  count: 1284,
  createdLast4Weeks: 385,
  createdLast12Weeks: 460,
  weeklyCreated: [8, 10, 9, 11, 7, 12, 10, 8, 9, 14, 12, 350],
  weeksObserved: 12,
  currentWeekPartial: true,
};

const detail: ForkDetail = {
  id: "fork-1",
  fullName: "pallets/flask",
  url: "https://github.com/pallets/flask",
  isFork: true,
  updatedAt: "2026-09-11T00:00:00Z",
  classification: "specialized",
  maintenance: "maintained",
  originalWorkPercent: 12,
  activity30d: 2,
  activity90d: 6,
  uniqueCommits: 9,
  uniquePatches: 4,
  confidence: 0.6,
  dataCoverage: 70,
  analysisDepth: "structural",
  evidenceCounts: { commits: 9, patches: 4, files: 3, releases: 0 },
  scoreComponents: [{ key: "popularity", label: "Popularity", value: 12 }],
  missingData: [],
  defaultBranch: "main",
  ahead: 4,
  behind: 1,
  classificationReasons: ["Distinct adapter changes"],
  evidence: [],
  branchPlan: [],
  starGrowth: growth,
};

describe("StarGrowthPanel", () => {
  it("renders count, windows, sparkline, and indicator-not-proof copy", () => {
    render(<StarGrowthPanel growth={growth} />);

    const panel = screen.getByRole("region", { name: "Star growth" });
    expect(panel).toHaveTextContent("1,284");
    expect(panel).toHaveTextContent("Created last 4 weeks");
    expect(panel).toHaveTextContent("385");
    expect(panel).toHaveTextContent("Created last 12 weeks");
    expect(panel).toHaveTextContent("460");
    expect(panel).toHaveTextContent("not proof of quality");
    expect(panel).toHaveTextContent("Newest week may be incomplete");
    expect(panel).toHaveTextContent("35×");
    expect(
      screen.getByRole("img", {
        name: /Weekly created stars, oldest to newest/,
      }),
    ).toBeInTheDocument();
    expect(panel).not.toHaveTextContent("vs upstream");
  });

  it("appends a vs-upstream created-star line for true forks", () => {
    render(
      <StarGrowthPanel
        growth={{
          ...growth,
          createdLast4Weeks: 87,
          createdLast12Weeks: 296,
          vsUpstream: {
            fullName: "deskflow/deskflow",
            createdLast4Weeks: 694,
            createdLast12Weeks: 2075,
            ratio4Weeks: 0.13,
            ratio12Weeks: 0.14,
          },
        }}
      />,
    );

    const panel = screen.getByRole("region", { name: "Star growth" });
    expect(panel).toHaveTextContent(
      "vs upstream deskflow/deskflow: 4w 87 vs 694 (0.13×), 12w 296 vs 2,075 (0.14×). Created-stars; current week may be partial; not quality.",
    );
    expect(panel).toHaveTextContent("not proof of quality");
  });

  it("renders nothing when star growth was not retrieved", () => {
    const { container } = render(<StarGrowthPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not inflate zero-star weeks on the sparkline", () => {
    const { container } = render(
      <StarGrowthPanel growth={{ ...growth, weeklyCreated: [0, 10, 0] }} />,
    );
    const bars = container.querySelectorAll(".star-sparkline-bar");
    expect(bars[0]).toHaveStyle({ height: "0%" });
    expect(bars[1]).not.toHaveStyle({ height: "0%" });
    expect(bars[2]).toHaveStyle({ height: "0%" });
  });
});

describe("EvidenceInspector", () => {
  it("shows star growth on the evidence panel", () => {
    render(
      <EvidenceInspector
        detail={detail}
        isLoading={false}
        onClose={() => undefined}
        analysisId="analysis-1"
      />,
    );

    expect(
      screen.getByRole("region", { name: "Star growth" }),
    ).toHaveTextContent("1,284");
    expect(screen.getByText("Score inputs")).toBeInTheDocument();
  });
});
