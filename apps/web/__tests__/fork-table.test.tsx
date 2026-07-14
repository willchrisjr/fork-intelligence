import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ForkTable } from "@/components/fork-table";
import type { ForkPage, ForkSummary } from "@/lib/types";

const fork = (id: string, name: string): ForkSummary => ({
  id,
  fullName: name,
  url: `https://github.com/${name}`,
  isFork: true,
  updatedAt: "2026-07-13T00:00:00Z",
  classification: "maintained_continuation",
  maintenance: "actively_maintained",
  originalWorkPercent: 42.3,
  activity30d: 12,
  activity90d: 44,
  uniqueCommits: 104,
  confidence: 0.9,
  dataCoverage: 88,
  analysisDepth: "structural",
  evidenceCounts: { commits: 4, patches: 3, files: 2, releases: 1 },
  scoreComponents: [],
  missingData: [],
});

const page: ForkPage = {
  items: [fork("a", "team/project"), fork("b", "labs/project")],
  total: 2,
  page: 1,
  pageSize: 25,
  availableClassifications: ["maintained_continuation"],
  partial: false,
  updatedAt: "2026-07-13T00:00:00Z",
};

describe("ForkTable", () => {
  it("provides keyboard-selectable comparison and evidence controls", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onInspect = vi.fn();
    render(
      <ForkTable
        page={page}
        analysisId="analysis-1"
        selected={[]}
        sort="maintained_successor"
        order="desc"
        onSort={vi.fn()}
        onSelect={onSelect}
        onInspect={onInspect}
        onPage={vi.fn()}
      />,
    );
    await user.click(
      screen.getByRole("checkbox", { name: /select team\/project/i }),
    );
    expect(onSelect).toHaveBeenCalledWith("a");
    await user.click(screen.getByRole("button", { name: "team/project" }));
    expect(onInspect).toHaveBeenCalledWith("a");
    expect(
      screen.getByRole("columnheader", { name: /confidence/i }),
    ).toHaveAttribute("aria-sort", "descending");
  });
});
