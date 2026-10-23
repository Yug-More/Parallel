import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  workers: 1,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:15175', trace: 'retain-on-failure' },
  webServer: [
    { command: `${process.env.PARALLEL_TEST_PYTHON || 'python'} ../backend/tests/e2e_server.py`, url: 'http://127.0.0.1:18001/health', reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 15175 --strictPort', env: { VITE_API_BASE: 'http://127.0.0.1:18001' }, url: 'http://127.0.0.1:15175', reuseExistingServer: false },
  ],
});
