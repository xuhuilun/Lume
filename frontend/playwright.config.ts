import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 40_000,
  workers: 1,
  use: {
    baseURL: process.env.LUME_UI_BASE_URL || "http://127.0.0.1:8000",
    browserName: "chromium",
    viewport: { width: 1440, height: 960 },
    trace: "off",
  },
});
