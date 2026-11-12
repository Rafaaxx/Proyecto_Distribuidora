import { defineConfig, devices } from '@playwright/test'

/**
 * Suite de aceptación de la etapa 1 (change 28, D13, D14; `docs/02-arquitectura.md` §15, §16.1).
 *
 * Corre en este equipo contra el compose de producción levantado por `scripts/aceptacion.mjs`
 * (`npm run test:e2e`), que pasa la dirección en `ACEPTACION_URL`. Un entorno ya levantado se
 * puede usar directamente: `ACEPTACION_URL=https://localhost:8443 npx playwright test`.
 *
 * Es UNA historia en serie, en el orden de la demostración (`00` §9): cada criterio usa lo que
 * dejó el anterior, así que no hay paralelismo y la primera falla frena todo (`maxFailures: 1`):
 * lo que sigue queda como «no corrido», no como fallido. Para ver todas las fallas de una
 * pantalla mientras se desarrolla: `--max-failures=0`.
 *
 * Solo Chromium. «PC» (Chrome de escritorio) para `/admin`; «teléfono» (emulación de un Pixel:
 * pantalla, toque, sin ratón) para `/ruta`. Los criterios de teléfono dependen del proyecto «PC»
 * (cargan lo que él deja); un test de teléfono que necesita la vista de PC abre su propio
 * contexto con `apoyo/contextos.ts`.
 */
const url = process.env.ACEPTACION_URL ?? 'https://localhost:8443'

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.ts',
  globalSetup: './tests/e2e/apoyo/calentamiento.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  maxFailures: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL: url,
    // El certificado lo firma la autoridad propia de Caddy (`CADDY_TLS=internal`): solo en la prueba.
    ignoreHTTPSErrors: true,
    // Con `ignoreHTTPSErrors` solo, Chromium rechaza registrar el service worker («SSL certificate
    // error occurred when fetching the script»): sin él no hay prueba sin conexión sobre el build.
    launchOptions: { args: ['--ignore-certificate-errors'] },
    locale: 'es-AR',
    timezoneId: 'America/Argentina/Mendoza',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'PC',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/00-humo.spec.ts', '**/0[1-3]-*.spec.ts'],
    },
    {
      name: 'teléfono',
      use: { ...devices['Pixel 7'] },
      dependencies: ['PC'],
      testMatch: ['**/0[4-9]-*.spec.ts', '**/1[01]-*.spec.ts', '**/aislamiento-y-permisos.spec.ts'],
    },
  ],
})
