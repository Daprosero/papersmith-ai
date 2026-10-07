import { defineConfig, devices } from '@playwright/test';

/**
 * Browser checks for the Paper Command Center.
 *
 * These run against the real FastAPI server from
 * `skills/_core/command_center/server.py`, serving the committed bundle in
 * `skills/_core/command_center/static/`. Checking `vite preview` instead would
 * verify a stand-in: the server we ship resolves assets differently and
 * validates the `Host` header, and both have broken the dashboard before.
 *
 * Port 8099 is deliberate. The server's own allow-list accepts
 * `127.0.0.1:<port>` on a loopback bind, so no `--allowed-host` is needed, and
 * 8099 stays clear of the 8080 default a developer is likely to be running.
 *
 * Vitest owns `src/**\/*.test.*`; this owns `e2e/**\/*.spec.ts`. They never
 * collide, and they are never the same command.
 */
const PORT = 8099;
const REPO_ROOT = new URL('..', import.meta.url).pathname;

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  // A layout assertion that fails because a neighbour shifted is a real
  // failure, not a flake to retry away.
  retries: 0,
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      // The stylesheet turns the element panel into a bottom sheet under 900px;
      // that breakpoint needs a viewport that actually crosses it.
      name: 'narrow',
      use: { ...devices['Desktop Chrome'], viewport: { width: 820, height: 900 } },
      testMatch: '**/layout.spec.ts',
    },
  ],
  webServer: {
    command: `.venv/bin/python -m skills._core.command_center.server --port ${PORT} --no-browser --log-level warning`,
    cwd: REPO_ROOT,
    url: `http://127.0.0.1:${PORT}/api/state`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
