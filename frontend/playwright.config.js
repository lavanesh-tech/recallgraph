import { defineConfig, devices } from "@playwright/test";

// Full stack: real FastAPI (port 8001) + real Postgres + Vite dev server with its /api proxy.
// Locally the running API/Vite are reused; in CI both are started here.
const ci = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: ci ? 1 : 0,
  reporter: ci ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "cd ../backend && uv run uvicorn recallgraph.main:create_app --factory --host 127.0.0.1 --port 8001",
      url: "http://127.0.0.1:8001/api/v1/health",
      reuseExistingServer: !ci,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !ci,
      timeout: 60_000,
    },
  ],
});
