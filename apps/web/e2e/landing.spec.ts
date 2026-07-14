import { expect, test } from "@playwright/test";
import { installApiMocks } from "./mocks";

test.describe("repository submission", () => {
  test("validates input without contacting the API", async ({ page }) => {
    const log = await installApiMocks(page);
    await page.goto("/");

    await expect(
      page.getByRole("heading", {
        name: "Find the forks that actually matter.",
      }),
    ).toBeVisible();
    await page.getByLabel("GitHub repository").fill("not a repository");
    await page.getByRole("button", { name: "Analyze repository" }).click();

    await expect(
      page.getByRole("alert").filter({
        hasText:
          "Enter owner/repository or a public github.com repository URL.",
      }),
    ).toHaveText(
      "Enter owner/repository or a public github.com repository URL.",
    );
    expect(log.createdAnalyses).toHaveLength(0);
  });

  test("submits a canonical public repository and selected intent", async ({
    page,
  }) => {
    const log = await installApiMocks(page);
    await page.goto("/");

    await page
      .getByLabel("GitHub repository")
      .fill("https://github.com/upstream/project/");
    await page
      .getByRole("radio", { name: "Find maintained successor" })
      .check();
    await page.getByRole("button", { name: "Analyze repository" }).click();

    await expect(page).toHaveURL(/\/analyses\/analysis-1$/);
    expect(log.createdAnalyses).toEqual([
      { repository: "https://github.com/upstream/project", mode: "successor" },
    ]);
    await expect(
      page.getByText("upstream/project", { exact: true }).first(),
    ).toBeVisible();
  });

  test("surfaces a safe API error without losing the form", async ({
    page,
  }) => {
    await installApiMocks(page, {
      createError: {
        status: 503,
        message: "The analysis queue is temporarily unavailable.",
      },
    });
    await page.goto("/");
    await page.getByLabel("GitHub repository").fill("upstream/project");
    await page.getByRole("button", { name: "Analyze repository" }).click();

    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: "The analysis queue is temporarily unavailable." }),
    ).toHaveText("The analysis queue is temporarily unavailable.");
    await expect(page.getByLabel("GitHub repository")).toHaveValue(
      "upstream/project",
    );
  });
});
