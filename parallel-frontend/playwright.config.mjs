import process from "node:process";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

process.env.PARALLEL_E2E_OUTBOX ||= join(
  tmpdir(),
  `parallel-e2e-outbox-${randomUUID()}`,
);
export default defineConfig({
  testDir: "./tests",
  globalTeardown: "./tests/cleanup.mjs",
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:15175",
    trace: "retain-on-failure",
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },
  webServer: [
    {
      command: `${process.env.PARALLEL_TEST_PYTHON || "python"} ../backend/tests/e2e_server.py`,
      env: { PARALLEL_E2E_OUTBOX: process.env.PARALLEL_E2E_OUTBOX },
      url: "http://127.0.0.1:18001/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 15175 --strictPort",
      env: { VITE_API_BASE: "http://127.0.0.1:18001" },
      url: "http://127.0.0.1:15175",
      reuseExistingServer: false,
    },
  ],
});
