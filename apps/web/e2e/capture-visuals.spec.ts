import { expect, test } from "@playwright/test";
import { installApiMocks } from "./mocks";

test.skip(
  process.env.CAPTURE_VISUALS !== "1",
  "Run only for explicit visual review artifacts.",
);

test.describe.configure({ mode: "serial" });

test("captures the landing reference viewport", async ({ page }) => {
  await installApiMocks(page);
  await page.setViewportSize({ width: 1568, height: 1002 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Find the forks that actually matter." }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/fork-intelligence-e2e/landing-1568x1002.png",
    fullPage: true,
  });
});

test("captures the analysis workspace reference viewport", async ({ page }) => {
  await installApiMocks(page);
  await page.setViewportSize({ width: 1680, height: 936 });
  await page.goto("/analyses/analysis-1");
  await expect(
    page.getByRole("button", { name: "lab/next", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/fork-intelligence-e2e/workspace-1680x936.png",
    fullPage: true,
  });
});

test("captures the comparison reference viewport", async ({ page }) => {
  await installApiMocks(page);
  await page.setViewportSize({ width: 1680, height: 944 });
  await page.goto("/comparisons/comparison-1");
  await expect(
    page.getByRole("heading", { name: "Change overlap" }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/fork-intelligence-e2e/comparison-1680x944.png",
    fullPage: true,
  });
});
