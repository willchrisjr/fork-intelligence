import { expect, test } from "@playwright/test";
import { installApiMocks } from "./mocks";

test.describe("investigation routes", () => {
  test("renders evidence-backed fork detail", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/analyses/analysis-1/forks/repo-b");

    await expect(
      page.getByRole("heading", { name: "Specialized" }),
    ).toBeVisible();
    await expect(
      page.getByText("Binary blob hydration was capped"),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Why this classification" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Score components" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Evidence", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("API adapter changes")).toBeVisible();
  });

  test("renders a three-repository comparison and evidence matrix", async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto("/comparisons/comparison-1");

    const compared = page.getByRole("region", {
      name: "Compared repositories",
    });
    await expect(compared).toContainText("upstream/project");
    await expect(compared).toContainText("lab/next");
    await expect(compared).toContainText("signal/edge");
    await expect(
      page.getByRole("heading", { name: "Change overlap" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Change composition" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Integration considerations" }),
    ).toBeVisible();
    await expect(page.getByText("Shared retry patch")).toBeVisible();
    await expect(
      page.getByText("Binary similarity was not calculated"),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Export report" }),
    ).toHaveAttribute("href", "/api/v1/analyses/analysis-1/exports/markdown");
  });

  test("renders deterministic development directions with method labels", async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto("/analyses/analysis-1/directions");

    await expect(
      page.getByRole("heading", { name: "Development directions" }),
    ).toBeVisible();
    await expect(page.getByText("Labels are heuristic.")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Runtime reliability" }),
    ).toBeVisible();
    await expect(page.getByText("complete-link-v1").first()).toBeVisible();
    await expect(
      page.getByText("src/runtime · tests/integration"),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "View cluster graph" }),
    ).toHaveAttribute(
      "href",
      "/analyses/analysis-1/evolution?graphMode=cluster",
    );
  });
});
