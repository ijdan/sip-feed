import { defineConfig, devices } from '@playwright/test';

/**
 * Configuration Playwright pour les tests E2E de Sip-feed.
 *
 * Pré-requis pour lancer les tests :
 *   ./start-emulator.sh   # émulateur Firestore :8080
 *   ./start-local.sh      # backend :8000 + frontend :3000
 *
 * Puis :
 *   npm run e2e           # mode headless
 *   npm run e2e:ui        # mode UI interactive
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // les tests partagent l'état Firestore, on évite les races
  retries: 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
