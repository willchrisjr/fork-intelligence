import { expect, test } from "@playwright/test";
import { analysisFixture, installApiMocks } from "./mocks";

const FALLBACK_ACCESS = {
  credential_mode: "anonymous",
  quota: { limit: 60, remaining: 12, resource: "core" },
  transitions: [
    {
      from_mode: "authenticated",
      to_mode: "anonymous",
      reason: "operator_credential_quota_exhausted",
      coverage_limitation: "Anonymous access lowers the rate limit.",
    },
  ],
  coverage_limitations: ["Anonymous access lowers the rate limit."],
  access_condition: null,
};

const CAPPED_PLAN = {
  planner_version: "2026.07.2",
  effective_cap: 2,
  counts: {
    considered: 6,
    selected: 2,
    excluded_by_cap: 3,
    unevaluated: 1,
    structurally_analyzed: 2,
  },
  selection_reasons: { branch_cap_exceeded: 3, default_branch: 2 },
  structural_coverage_default_only: false,
};

test.describe("provider and branch-plan disclosures", () => {
  test("shows the effective access mode and branch coverage on a completed analysis", async ({
    page,
  }) => {
    await installApiMocks(page, {
      analysis: analysisFixture({
        status: "completed",
        progress: 100,
        access: FALLBACK_ACCESS,
        branch_plan: CAPPED_PLAN,
      }),
    });
    await page.goto("/analyses/analysis-1");

    await expect(page.getByTestId("credential-mode")).toHaveText("Anonymous");
    await expect(page.getByTestId("quota-remaining")).toHaveText("20%");
    await expect(page.getByTestId("access-transitions")).toContainText(
      "operator credential quota exhausted",
    );

    // A sampling choice and missing data must read as different figures.
    await expect(page.getByTestId("branch-excluded-by-cap")).toHaveText("3");
    await expect(page.getByTestId("branch-unevaluated")).toHaveText("1");
    await expect(page.getByTestId("branch-structurally-analyzed")).toHaveText(
      "2",
    );
  });

  test("keeps partial results visible while disclosing an unavailable provider", async ({
    page,
  }) => {
    await installApiMocks(page, {
      analysis: analysisFixture({
        status: "partial",
        progress: 46,
        access: {
          ...FALLBACK_ACCESS,
          access_condition: {
            code: "github_rate_limited",
            message: "GitHub access could not continue.",
            resumable: true,
          },
        },
        branch_plan: CAPPED_PLAN,
      }),
    });
    await page.goto("/analyses/analysis-1");

    await expect(page.getByTestId("access-condition")).toContainText(
      "GitHub access could not continue.",
    );
    // The disclosure must not replace the results already gathered.
    await expect(
      page.getByRole("region", { name: "Analysis summary" }),
    ).toBeVisible();
  });

  test("reports default-only structural coverage", async ({ page }) => {
    await installApiMocks(page, {
      analysis: analysisFixture({
        status: "completed",
        progress: 100,
        access: FALLBACK_ACCESS,
        branch_plan: {
          ...CAPPED_PLAN,
          structural_coverage_default_only: true,
        },
      }),
    });
    await page.goto("/analyses/analysis-1");

    await expect(page.getByTestId("default-only-coverage")).toContainText(
      "did not extend beyond the default branch",
    );
  });

  test("omits the disclosures for an analysis that predates them", async ({
    page,
  }) => {
    await installApiMocks(page, {
      analysis: analysisFixture({ status: "completed", progress: 100 }),
    });
    await page.goto("/analyses/analysis-1");

    // An empty panel would imply the run had no credential at all.
    await expect(page.getByTestId("credential-mode")).toHaveCount(0);
    await expect(page.getByTestId("branch-considered")).toHaveCount(0);
    await expect(
      page.getByRole("region", { name: "Analysis summary" }),
    ).toBeVisible();
  });

  test("stacks the disclosures readably on a narrow viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installApiMocks(page, {
      analysis: analysisFixture({
        status: "completed",
        progress: 100,
        access: FALLBACK_ACCESS,
        branch_plan: CAPPED_PLAN,
      }),
    });
    await page.goto("/analyses/analysis-1");

    const accessPanel = page.getByRole("region", { name: "Provider access" });
    const branchPanel = page.getByRole("region", { name: "Branch coverage" });
    await expect(accessPanel).toBeVisible();
    await expect(branchPanel).toBeVisible();

    const accessBox = await accessPanel.boundingBox();
    const branchBox = await branchPanel.boundingBox();
    // Stacked, not side by side, so the figures stay legible on a phone.
    expect(accessBox && branchBox).toBeTruthy();
    if (accessBox && branchBox) {
      expect(branchBox.y).toBeGreaterThan(accessBox.y + accessBox.height - 1);
      expect(branchBox.x + branchBox.width).toBeLessThanOrEqual(390);
    }
  });
});
