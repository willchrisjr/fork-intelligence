import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: true,
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile-portrait",
      use: { ...devices["Pixel 7"] },
      testMatch: /evolution\.spec\.ts/,
    },
    {
      name: "mobile-landscape",
      use: { ...devices["Pixel 7 landscape"] },
      testMatch: /evolution\.spec\.ts/,
    },
  ],
  webServer: {
    command:
      "../node_modules/.bin/next start .. --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
