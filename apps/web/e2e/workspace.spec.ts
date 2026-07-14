import { expect, test } from "@playwright/test";
import { analysisFixture, installApiMocks } from "./mocks";

test.describe("analysis workspace", () => {
  test("shows progressive partial results, quota warning, exports, and cancellation", async ({
    page,
  }) => {
    const log = await installApiMocks(page, {
      analysis: analysisFixture({
        status: "partial",
        progress: 58,
        quota_snapshot: {
          remaining_percent: 2,
          resets_at: "2026-07-13T19:00:00Z",
        },
        warnings: [
          { message: "GitHub API rate limit reached; retry is checkpointed." },
        ],
      }),
      partialForks: true,
    });
    await page.goto("/analyses/analysis-1");

    await expect(
      page.getByText("Partial results", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Results are partial.")).toBeVisible();
    await expect(
      page.getByText("GitHub API rate limits are delaying analysis."),
    ).toBeVisible();
    await expect(page.getByLabel("Analysis summary")).toContainText("48");
    await expect(page.getByLabel("Analysis navigation")).toContainText(
      "Git analysis",
    );
    await expect(page.getByRole("table").first()).toContainText("lab/next");

    await page.getByText("Export", { exact: true }).click();
    await expect(
      page.getByRole("link", { name: "JSON analysis" }),
    ).toHaveAttribute("href", "/api/v1/analyses/analysis-1/exports/json");
    await expect(
      page.getByRole("link", { name: "CSV fork table" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Markdown report" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect.poll(() => log.cancelled).toBe(1);
  });

  test("filters and ranks forks through shareable URL state", async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto("/analyses/analysis-1");
    await expect(
      page.getByRole("button", { name: "lab/next", exact: true }),
    ).toBeVisible();

    await page.getByLabel("Ranking profile").selectOption("recent_activity");
    await expect(page).toHaveURL(/sort=recent_activity/);
    await expect(
      page.getByRole("columnheader", { name: "Activity" }),
    ).toHaveAttribute("aria-sort", "descending");

    await page.getByLabel("Search forks").fill("signal");
    await expect(page).toHaveURL(/q=signal/);
    await expect(
      page.getByRole("button", { name: "signal/edge", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "lab/next", exact: true }),
    ).toHaveCount(0);

    await page.getByLabel("Analysis depth filter").selectOption("structural");
    await expect(page).toHaveURL(/depth=structural/);
    await expect(
      page.getByRole("button", { name: "signal/edge", exact: true }),
    ).toBeVisible();
  });

  test("selects two forks and creates an upstream-inclusive comparison", async ({
    page,
  }) => {
    const log = await installApiMocks(page);
    await page.goto("/analyses/analysis-1");

    await page.getByLabel("Select lab/next for comparison").click();
    await expect(
      page.getByText("1 of 2 forks selected · upstream included"),
    ).toBeVisible();
    await page.getByLabel("Select signal/edge for comparison").click();
    await expect(
      page.getByText("2 of 2 forks selected · upstream included"),
    ).toBeVisible();
    await page.getByRole("button", { name: "Compare selected" }).click();

    await expect(page).toHaveURL(/\/comparisons\/comparison-1$/);
    expect(log.createdComparisons).toEqual([
      { repository_ids: ["repo-upstream", "repo-a", "repo-b"] },
    ]);
    await expect(
      page.getByRole("region", { name: "Compared repositories" }),
    ).toContainText("upstream/project");
  });

  test("opens inspectable evidence and full fork details", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/analyses/analysis-1");

    await page
      .getByRole("button", { name: "Inspect evidence for lab/next" })
      .click();
    const inspector = page.getByRole("complementary", {
      name: "Evidence inspector",
    });
    await expect(inspector).toBeVisible();
    await expect(inspector).toContainText("Retry-safe transaction patch");
    await expect(inspector).toContainText(
      "Nineteen patches are not present upstream.",
    );
    await inspector
      .getByRole("link", { name: "Open full fork details" })
      .click();

    await expect(page).toHaveURL(/\/forks\/repo-a$/);
    await expect(
      page.getByRole("heading", { name: "Maintained continuation" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "History relationship" }),
    ).toBeVisible();
    await expect(page.getByText("f00dbabe1234567890")).toBeVisible();
  });

  test("labels rate-limited fork data and retains a retry path", async ({
    page,
  }) => {
    await installApiMocks(page, {
      forksError: {
        status: 429,
        message: "Anonymous GitHub quota is exhausted.",
      },
    });
    await page.goto("/analyses/analysis-1");

    await expect(
      page.getByRole("heading", { name: "Fork results are rate limited" }),
    ).toBeVisible();
    await expect(
      page.getByText("Anonymous GitHub quota is exhausted."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Retry results" }),
    ).toBeVisible();
    await expect(page.getByText("48").first()).toBeVisible();
  });

  test("shows an analysis-level error and retry action", async ({ page }) => {
    await installApiMocks(page, {
      analysisError: { status: 404, message: "This analysis does not exist." },
    });
    await page.goto("/analyses/analysis-1");

    await expect(
      page.getByRole("heading", { name: "Analysis unavailable" }),
    ).toBeVisible();
    await expect(page.getByText("This analysis does not exist.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("offers resume for a cancelled checkpoint", async ({ page }) => {
    const log = await installApiMocks(page, {
      analysis: { status: "cancelled", progress: 64 },
    });
    await page.goto("/analyses/analysis-1");

    await expect(
      page.getByText("Analysis cancelled", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Resume" }).click();
    await expect.poll(() => log.resumed).toBe(1);
  });
});
