import { defineConfig, devices } from '@playwright/test';

const testPort = process.env.PLAYWRIGHT_PORT || '3100';
const testBaseURL = `http://127.0.0.1:${testPort}`;

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: true,
  timeout: 60_000,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: testBaseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
  ],
  webServer: {
    command: `node node_modules/next/dist/bin/next dev -H 127.0.0.1 -p ${testPort}`,
    url: testBaseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
