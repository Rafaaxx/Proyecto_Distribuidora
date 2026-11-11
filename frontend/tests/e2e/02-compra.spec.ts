/**
 * Criterio 2 de `00` §9 (change 28, D14): compra a crédito de vino por caja y de cerveza por
 * unidad, a costos distintos; el stock, el costo promedio y la deuda con el proveedor son
 * correctos. Spec `sistema/aceptacion-etapa-1`, escenario «Criterio 2 — compra a crédito con
 * presentaciones y costos distintos». Cita CST-11, INV-12, INV-13, CMP-03.
 *
 * Valores esperados (la organización es monotributista: el valor pagado ES el costo, CST-06):
 *   Vino A:     stock 31 a $1.000 + 10 cajas x6 (60 botellas) a $6.600 la caja ($1.100 c/u)
 *               = 91 botellas, promedio (31.000 + 66.000) / 91 = $1.065,934066;
 *               deuda con Bodega del Valle: 50.000 (saldo inicial) + 66.000 = 116.000.
 *   Cerveza B:  stock 31 a $1.500 + 100 latas sueltas a $1.600
 *               = 131 latas, promedio (46.500 + 160.000) / 131 = $1.576,335878;
 *               deuda con Cervecería Andina: 160.000.
 */
import type { Page } from '@playwright/test'

import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { expect, test } from './apoyo/fixtures'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

interface LineaDeCompra {
  producto: string
  presentacion: string
  cantidad: string
  valor: string
}

async function registrarCompraACredito(page: Page, proveedor: string, linea: LineaDeCompra): Promise<void> {
  await page.goto('/admin/compras/nueva')
  await page.getByLabel('Proveedor').selectOption({ label: proveedor })
  await page.getByLabel('Ubicación de destino').selectOption({ label: 'Depósito central' })
  await expect(page.getByLabel('Condición')).toHaveValue('CREDITO')

  await page.getByLabel('Producto').selectOption({ label: linea.producto })
  await page.getByLabel('Presentación').selectOption({ label: linea.presentacion })
  await page.getByLabel('Cantidad', { exact: true }).fill(linea.cantidad)
  await page.getByRole('textbox', { name: 'Valor pagado' }).fill(linea.valor)

  await page.getByRole('button', { name: 'Confirmar compra' }).click()
  await expect(page.getByRole('heading', { name: 'Compra registrada' })).toBeVisible()
}

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 2 — compra a crédito con presentaciones y costos distintos', () => {
  test('se registra la compra de vino por caja', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'ges01')

    await registrarCompraACredito(page, 'Bodega del Valle', {
      producto: 'Vino A',
      presentacion: 'Caja x6',
      cantidad: '10',
      valor: '6600',
    })

    await expect(page.getByTestId('resultado-total-factura')).toContainText('66.000,00')
    // CMP-04: el sistema ofrece, sin hacerlo solo, dejar este costo como informado (lo usa el criterio 3).
    await page.getByRole('button', { name: 'Registrar como costo informado' }).click()
    await expect(page.getByText('Costo informado registrado.')).toBeVisible()
  })

  test('se registra la compra de cerveza por unidad', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'ges01')

    await registrarCompraACredito(page, 'Cervecería Andina', {
      producto: 'Cerveza B',
      presentacion: 'Lata',
      cantidad: '100',
      valor: '1600',
    })

    await expect(page.getByTestId('resultado-total-factura')).toContainText('160.000,00')
    await page.getByRole('button', { name: 'Registrar como costo informado' }).click()
    await expect(page.getByText('Costo informado registrado.')).toBeVisible()
  })

  test('el stock, el costo promedio y la deuda con cada proveedor coinciden con lo esperado', async ({
    browser,
    baseURL,
  }) => {
    const consultas = new Consultas(await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'ges01'))

    expect(await consultas.stockBase('Depósito central', 'VINO-A')).toBe(91)
    expect(await consultas.stockBase('Depósito central', 'CERV-B')).toBe(131)
    // CST-11, a 6 decimales.
    expect(await consultas.costoPromedio('VINO-A')).toEqual({ costo: '1065.934066', stockTotal: 91 })
    expect(await consultas.costoPromedio('CERV-B')).toEqual({ costo: '1576.335878', stockTotal: 131 })
    expect(await consultas.saldoDeProveedor('Bodega del Valle')).toBe('116000.00')
    expect(await consultas.saldoDeProveedor('Cervecería Andina')).toBe('160000.00')
  })
})
