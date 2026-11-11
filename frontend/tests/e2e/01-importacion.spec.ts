/**
 * Criterio 1 de `00` §9 (change 28, D14): importación de productos, clientes y proveedores desde
 * planillas, y carga de stock inicial y saldos iniciales. Spec `sistema/aceptacion-etapa-1`,
 * escenario «Criterio 1 — importación y saldos iniciales». Cita IMP-01, IMP-04, IMP-06, STK-10,
 * CC-08, INV-12, INV-13.
 *
 * La importación la hace `admin`: `IMPORTAR_DATOS` es solo del Administrador (`01` §19), no de
 * `Administración` (`ges01`).
 */
import path from 'node:path'

import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { expect, test } from './apoyo/fixtures'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

const DATOS = path.join(import.meta.dirname, 'datos')

// El orden es el de la puesta en marcha: cada tipo referencia a los anteriores (IMP-04).
const PLANILLAS = [
  { tipo: 'Proveedores', archivo: 'proveedores.csv', filas: 2 },
  { tipo: 'Productos', archivo: 'productos.csv', filas: 4 },
  { tipo: 'Clientes', archivo: 'clientes.csv', filas: 2 },
  { tipo: 'Stock inicial', archivo: 'stock-inicial.csv', filas: 2 },
  { tipo: 'Saldos iniciales', archivo: 'saldos-iniciales.csv', filas: 3 },
] as const

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 1 — importación y saldos iniciales', () => {
  test('el administrador importa las cinco planillas desde /admin', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/importacion')

    for (const { tipo, archivo, filas } of PLANILLAS) {
      await page.getByLabel('Tipo de importación').selectOption({ label: tipo })
      await page.getByLabel('Archivo').setInputFiles(path.join(DATOS, archivo))
      await page.getByRole('button', { name: 'Importar', exact: true }).click()

      await expect(page.getByRole('status')).toHaveText(`${String(filas)} filas importadas`)
    }
  })

  test('los maestros importados se ven en sus pantallas', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')

    await page.goto('/admin/catalogo/productos')
    await expect(page.getByText('Vino A', { exact: true })).toBeVisible()
    await expect(page.getByText('Cerveza B', { exact: true })).toBeVisible()

    await page.goto('/admin/clientes')
    await expect(page.getByText('Almacén Don Pedro')).toBeVisible()
    await expect(page.getByText('Kiosco La Esquina')).toBeVisible()

    await page.goto('/admin/proveedores')
    await expect(page.getByText('Bodega del Valle')).toBeVisible()
    await expect(page.getByText('Cervecería Andina')).toBeVisible()
  })

  test('el stock y los saldos iniciales quedan cargados con sus valores', async ({ browser, baseURL }) => {
    const consultas = new Consultas(await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin'))

    // STK-10: 31 botellas de Vino A (5 cajas + 1 unidad, CAT-08) y 31 latas de Cerveza B.
    expect(await consultas.stockBase('Depósito central', 'VINO-A')).toBe(31)
    expect(await consultas.stockBase('Depósito central', 'CERV-B')).toBe(31)
    // CST-11: el primer ingreso fija el promedio en el costo del ingreso.
    expect(await consultas.costoPromedio('VINO-A')).toEqual({ costo: '1000.000000', stockTotal: 31 })
    expect(await consultas.costoPromedio('CERV-B')).toEqual({ costo: '1500.000000', stockTotal: 31 })
    // CC-08: lo que nos deben los clientes y lo que le debemos al proveedor.
    expect(await consultas.saldoDeCliente('C001')).toBe('25000.00')
    expect(await consultas.saldoDeCliente('C002')).toBe('8000.00')
    expect(await consultas.saldoDeProveedor('Bodega del Valle')).toBe('50000.00')
  })

  test('una planilla con errores no importa ninguna fila (IMP-01)', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/importacion')

    await page.getByLabel('Tipo de importación').selectOption({ label: 'Proveedores' })
    // Bodega del Valle ya existe: es un duplicado (IMP-03) y se rechaza el archivo completo.
    await page.getByLabel('Archivo').setInputFiles(path.join(DATOS, 'proveedores.csv'))
    await page.getByRole('button', { name: 'Importar', exact: true }).click()

    await expect(page.getByText('No se importó ninguna fila')).toBeVisible()
  })
})
