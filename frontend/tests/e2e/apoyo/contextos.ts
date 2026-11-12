/**
 * Vistas de la suite (change 28, D14): «PC» (Chrome de escritorio, `/admin`) y «teléfono» (Pixel
 * emulado: pantalla, toque, sin ratón, `/ruta`). Cada proyecto de Playwright trae su vista por
 * defecto; una prueba que necesita la otra (por ejemplo, la PC que transfiere mercadería antes de
 * que el teléfono abra la jornada) abre un contexto aparte con esta función. La página queda
 * vigilada por el accesorio común (CSP y errores no manejados).
 */
import { devices, type Browser, type BrowserContext, type Page } from '@playwright/test'

import type { Vigilante } from './fixtures'

export type Vista = 'PC' | 'teléfono'

export interface PaginaAparte {
  context: BrowserContext
  page: Page
}

export async function abrirVista(
  browser: Browser,
  vigilante: Vigilante,
  vista: Vista,
  baseURL: string,
): Promise<PaginaAparte> {
  const dispositivo = vista === 'PC' ? devices['Desktop Chrome'] : devices['Pixel 7']
  const context = await browser.newContext({
    ...dispositivo,
    baseURL,
    ignoreHTTPSErrors: true,
    locale: 'es-AR',
    timezoneId: 'America/Argentina/Mendoza',
  })
  const page = await context.newPage()
  vigilante.vigilar(page)
  return { context, page }
}
