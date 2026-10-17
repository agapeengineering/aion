import { defineConfig, devices } from '@playwright/test';
const external = process.env.AION_BASE_URL;
export default defineConfig({
 testDir: './tests/e2e', fullyParallel: true, workers: process.env.CI ? 2 : 3, timeout: 30000,
 expect: { timeout: 8000 }, reporter: [['list'], ['html', { open: 'never' }]],
 use: { baseURL: external ?? 'http://127.0.0.1:4173', timezoneId: 'UTC', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
 projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }, { name: 'firefox', use: { ...devices['Desktop Firefox'] } }, { name: 'webkit', use: { ...devices['Desktop Safari'] } }],
 ...(!external ? { webServer: { command: 'pnpm preview', url: 'http://127.0.0.1:4173', reuseExistingServer: !process.env.CI } } : {}),
});
