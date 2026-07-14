import { expect, test } from "@playwright/test";
import { installApiMocks } from "./mocks";

test.describe("evolution and responsive access", () => {
  test("keeps graph conclusions synchronized with a keyboard-accessible table", async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto("/analyses/analysis-1/evolution");

    await expect(
      page.getByRole("heading", { name: "Repository evolution" }),
    ).toBeVisible();
    await expect(page.getByText("Showing 3 of 48")).toBeVisible();
    await expect(
      page.getByRole("img", {
        name: /Interactive lineage graph with 3 displayed repositories/,
      }),
    ).toBeVisible();

    const table = page.getByRole("table");
    await expect(table).toContainText("upstream/project");
    await expect(table).toContainText("lab/next");
    await expect(table).toContainText("signal/edge");
    await table.getByRole("button", { name: "lab/next" }).click();
    await expect(table.getByRole("row", { name: /lab\/next/ })).toHaveClass(
      /selected/,
    );

    await page.getByRole("button", { name: "cluster" }).click();
    await expect(page).toHaveURL(/graphMode=cluster/);
    await expect(
      page.getByRole("img", { name: /Interactive cluster graph/ }),
    ).toBeVisible();
    await page.getByLabel("Search graph repositories").fill("lab");
    await expect(page).toHaveURL(/graphSearch=lab/);

    await expect(page.getByRole("button", { name: "Zoom in" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Zoom out" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Reset graph view" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Step to next repository" }),
    ).toBeVisible();
  });

  test("keeps primary navigation and controls usable at the native viewport", async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto("/analyses/analysis-1/evolution");

    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();
    await expect(
      page.getByRole("heading", { name: "Repository evolution" }),
    ).toBeVisible();
    const mobileNavigation = page.getByRole("navigation", {
      name: "Mobile workspace navigation",
    });
    if ((await mobileNavigation.count()) > 0) {
      await expect(mobileNavigation).toBeVisible();
    } else {
      await expect(
        page.getByRole("complementary", { name: "Analysis navigation" }),
      ).toBeVisible();
    }
    await expect(
      page.getByRole("link", { name: "Evolution" }).first(),
    ).toHaveAttribute("aria-current", "page");
    await expect(page.getByLabel("Graph mode")).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(bodyWidth).toBeLessThanOrEqual(viewport!.width + 1);
  });
});
