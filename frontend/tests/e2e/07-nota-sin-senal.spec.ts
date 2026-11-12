/**
 * Criterio 7 de `00` §9 (change 28, D15): nota de venta sin señal. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Criterio 7 — nota de venta sin señal». Cita VTA-13,
 * INV-17.
 *
 * Lo que una prueba automática NO puede hacer: abrir la hoja de compartir del sistema ni WhatsApp
 * (no existen en un navegador automatizado). Por eso `navigator.share` se reemplaza por un espía
 * y la prueba comprueba que se genera un PDF de verdad y que se llama a la hoja de compartir
 * con ese archivo, sin red. El envío real por WhatsApp queda para la prueba manual (D15).
 */
import type { Page } from '@playwright/test'

import { expect, test } from './apoyo/fixtures'
import { exigir } from './apoyo/memoria'
import {
  abrirTelefono,
  guardarTelefono,
  problemasDelTelefono,
  recargarSinSenal,
  type Telefono,
} from './apoyo/telefono'

interface Compartido {
  nombre: string
  tipo: string
  tamano: number
  cabecera: string
  titulo: string
}

declare global {
  interface Window {
    __compartido?: Compartido[]
  }
}

/** Reemplaza la hoja de compartir del sistema por un espía que guarda lo que recibe. */
async function instalarEspiaDeCompartir(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.__compartido = []
    Object.defineProperty(navigator, 'canShare', { value: () => true, configurable: true })
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: async (datos: ShareData) => {
        const archivo = datos.files?.[0]
        const bytes = archivo === undefined ? new Uint8Array() : new Uint8Array(await archivo.arrayBuffer())
        window.__compartido?.push({
          nombre: archivo?.name ?? '',
          tipo: archivo?.type ?? '',
          tamano: archivo?.size ?? 0,
          cabecera: String.fromCharCode(...bytes.slice(0, 5)),
          titulo: datos.title ?? '',
        })
      },
    })
  })
}

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 7 — nota de venta sin señal', () => {
  let telefono: Telefono

  test.beforeAll(async ({ browser }, testInfo) => {
    telefono = await abrirTelefono(browser, testInfo.project.use.baseURL ?? '')
  })

  test.afterAll(async () => {
    await guardarTelefono(telefono)
    expect(problemasDelTelefono(telefono), 'el teléfono informó errores de seguridad o no manejados').toEqual([])
  })

  test('sin señal, la nota de la venta del criterio 5 se genera como PDF y se pasa a la hoja de compartir', async () => {
    const numero = exigir('numeroVenta5')
    await recargarSinSenal(telefono)
    const { page } = telefono

    await instalarEspiaDeCompartir(page)
    await page.getByRole('link', { name: 'Ventas de hoy' }).first().click()
    await page.getByRole('link', { name: new RegExp(numero) }).click()
    await expect(page.getByRole('heading', { name: `Venta ${numero}` })).toBeVisible()
    await expect(page.getByText('Sin enviar', { exact: true }).first()).toBeVisible()

    await page.getByRole('button', { name: 'Compartir nota' }).click()
    await expect.poll(() => page.evaluate(() => window.__compartido?.length ?? 0)).toBe(1)

    const [compartido] = await page.evaluate(() => window.__compartido ?? [])
    expect(compartido?.nombre).toBe(`nota-de-venta-${numero}.pdf`)
    expect(compartido?.tipo).toBe('application/pdf')
    expect(compartido?.cabecera).toBe('%PDF-')
    expect(compartido?.tamano).toBeGreaterThan(1000)
    expect(compartido?.titulo).toContain(numero)
    await expect(page.getByText(/No se pudo (generar|compartir)/)).toHaveCount(0)
  })

  test('sin señal también se puede descargar la nota', async () => {
    const numero = exigir('numeroVenta5')
    const { page } = telefono
    const descarga = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Descargar nota' }).click()
    expect((await descarga).suggestedFilename()).toBe(`nota-de-venta-${numero}.pdf`)
  })
})
