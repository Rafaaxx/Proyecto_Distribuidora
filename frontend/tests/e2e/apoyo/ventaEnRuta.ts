/**
 * Pasos de la pantalla «Vender» de `/ruta` que repiten los criterios 5 y 6 (change 28, D14).
 * Solo manejan la pantalla; lo que se afirma queda en cada criterio.
 */
import type { Page } from '@playwright/test'

import { expect } from '@playwright/test'

export async function abrirVender(page: Page, cliente: string): Promise<void> {
  await page.getByRole('link', { name: 'Vender' }).first().click()
  await expect(page.getByRole('heading', { name: 'Vender' })).toBeVisible()
  await page.getByRole('button', { name: new RegExp(cliente) }).click()
  await expect(page.getByText(`Cliente: ${cliente}`)).toBeVisible()
}

export async function cargarProducto(
  page: Page,
  producto: string,
  cantidades: { cajas?: number; unidades?: number },
): Promise<void> {
  await page.getByRole('button', { name: `Agregar ${producto}` }).click()
  if (cantidades.cajas !== undefined) await page.getByLabel(`Cajas de ${producto}`).fill(String(cantidades.cajas))
  if (cantidades.unidades !== undefined) await page.getByLabel(`Unidades de ${producto}`).fill(String(cantidades.unidades))
}

export async function cobrarCon(
  page: Page,
  numero: number,
  medio: string,
  importe: string,
  referencia?: string,
): Promise<void> {
  await page.getByRole('button', { name: 'Agregar medio de cobro' }).click()
  await page.getByLabel(`Medio de cobro ${String(numero)}`).selectOption({ label: medio })
  await page.getByLabel(`Importe del medio ${String(numero)}`).fill(importe)
  if (referencia !== undefined) await page.getByLabel(`Referencia del medio ${String(numero)}`).fill(referencia)
}
