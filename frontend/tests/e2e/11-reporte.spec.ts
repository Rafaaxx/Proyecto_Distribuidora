/**
 * Criterio 11 de `00` §9 (change 28, D14): el reporte concilia. Spec `sistema/aceptacion-etapa-1`,
 * escenario «Criterio 11 — el reporte concilia». Cita REP-01, REP-02, REP-04.
 *
 * `admin` abre el reporte de ventas del período (el mes en curso) y sus totales tienen que ser los
 * de las ventas NO anuladas que dejó la suite (la del criterio 3 y la del criterio 5); la venta
 * anulada del criterio 9 aparece aparte (REP-02). La utilidad es neto menos costo vendido.
 */
import Decimal from 'decimal.js'

import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { abrirVista } from './apoyo/contextos'
import { expect, test } from './apoyo/fixtures'
import { exigir } from './apoyo/memoria'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

interface ReporteDeVentas {
  resumen: {
    cantidad_ventas: number
    total: string
    importe_neto: string
    costo_vendido: string | null
    utilidad: string | null
  }
  anuladas: { cantidad: number; total: string }
}

function enPantalla(importe: Decimal): string {
  return new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    importe.toNumber(),
  )
}

test.describe('Criterio 11 — el reporte concilia', () => {
  test('los totales del reporte son los de las ventas no anuladas de la suite', async ({ browser, baseURL, vigilante }) => {
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const consultas = new Consultas(api)

    const ventas = await consultas.ventas()
    const confirmadas = ventas.filter((v) => v.estado === 'CONFIRMADA')
    const anuladas = ventas.filter((v) => v.estado === 'ANULADA')
    // Criterio 3 (admin), criterio 5 (teléfono) y la del criterio 6, anulada en el 9.
    expect(confirmadas).toHaveLength(2)
    expect(anuladas.map((v) => v.numero)).toEqual([exigir('numeroVenta6')])

    const totalEsperado = confirmadas.reduce((suma, v) => suma.plus(v.total), new Decimal(0))
    const detalles = await Promise.all(confirmadas.map((v) => consultas.detalleDeVenta(v.venta_id)))
    const lineas = detalles.flatMap((d) => d.lineas)
    const netoEsperado = lineas.reduce((suma, l) => suma.plus(l.importe_neto), new Decimal(0))
    const costoEsperado = lineas.reduce((suma, l) => suma.plus(l.costo_total ?? '0'), new Decimal(0))

    const reporte = await api.leer<ReporteDeVentas>('/api/v1/reportes/ventas')
    expect(reporte.resumen.cantidad_ventas).toBe(2)
    expect(new Decimal(reporte.resumen.total).toFixed(2)).toBe(totalEsperado.toFixed(2))
    expect(new Decimal(reporte.resumen.importe_neto).toFixed(2)).toBe(netoEsperado.toFixed(2))
    expect(new Decimal(reporte.resumen.costo_vendido ?? 'NaN').toFixed(2)).toBe(costoEsperado.toFixed(2))
    expect(new Decimal(reporte.resumen.utilidad ?? 'NaN').toFixed(2)).toBe(netoEsperado.minus(costoEsperado).toFixed(2))
    // REP-02: la anulada no suma; se informa aparte.
    expect(reporte.anuladas.cantidad).toBe(1)
    expect(new Decimal(reporte.anuladas.total).toFixed(2)).toBe(exigir('totalVenta6'))

    // Y la pantalla (vista de PC) muestra esas mismas cifras.
    const { page } = await abrirVista(browser, vigilante, 'PC', baseURL ?? '')
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/reportes')
    await expect(page.getByRole('heading', { name: 'Resumen del período' })).toBeVisible()
    const resumen = page.getByRole('region', { name: 'Resumen del período' })
    await expect(resumen).toContainText(enPantalla(totalEsperado))
    await expect(resumen).toContainText(enPantalla(netoEsperado.minus(costoEsperado)))
  })
})
