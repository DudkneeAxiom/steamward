import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 120000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: 'http://localhost:8123',
    viewport: { width: 1280, height: 800 },
  },
  webServer: {
    command: 'python3 -m http.server 8123',
    port: 8123,
    reuseExistingServer: true,
  },
});
