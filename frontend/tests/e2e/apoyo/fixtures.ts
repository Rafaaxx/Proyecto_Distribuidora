/**
 * Accesorio común de la suite de aceptación (change 28, D9, D14): toda prueba FALLA si el
 * navegador informa una violación de la política de seguridad de contenido (CSP) o un error no
 * manejado de la página. Spec `sistema/aceptacion-etapa-1`, requisito «La suite no tolera errores
 * de seguridad del navegador». Regla: `02` §18.
 *
 * Las pruebas importan `test` y `expect` de acá, no de `@playwright/test`.
 */
import { test as base, expect, type Page } from '@playwright/test'

import { directivaViolada, esViolacionDeCsp } from './csp'

export class Vigilante {
  violacionesDeCsp: string[] = []
  erroresDePagina: string[] = []

  /** Empieza a mirar una página (la del test, un contexto aparte o una ventana emergente). */
  vigilar(page: Page): void {
    page.on('console', (mensaje) => {
      if (mensaje.type() === 'error' && esViolacionDeCsp(mensaje.text())) {
        this.violacionesDeCsp.push(mensaje.text())
      }
    })
    page.on('pageerror', (error) => this.erroresDePagina.push(error.message))
  }

  /** Para una prueba que provoca la violación a propósito (la del propio accesorio). */
  descartarViolaciones(): void {
    this.violacionesDeCsp = []
  }

  descartarErrores(): void {
    this.erroresDePagina = []
  }

  /** Los problemas encontrados, nombrando la directiva violada; vacío si no hubo ninguno. */
  problemas(): string[] {
    return [
      ...this.violacionesDeCsp.map(
        (m) => `Violación de CSP (directiva ${directivaViolada(m) ?? 'desconocida'}): ${m}`,
      ),
      ...this.erroresDePagina.map((m) => `Error no manejado de la página: ${m}`),
    ]
  }
}

export const test = base.extend<{ vigilante: Vigilante }>({
  vigilante: [
    async ({ context }, use) => {
      const vigilante = new Vigilante()
      context.pages().forEach((page) => vigilante.vigilar(page))
      context.on('page', (page) => vigilante.vigilar(page))

      await use(vigilante)

      expect(vigilante.problemas(), 'el navegador informó errores de seguridad o no manejados').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
