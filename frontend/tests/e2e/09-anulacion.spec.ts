/**
 * Criterio 9 de `00` §9 (change 28, D14): anulación sin borrar historia. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Criterio 9 — anulación sin borrar historia». Cita
 * INV-05, INV-19, VTA-20, VTA-21, VTA-22.
 *
 * El rol Vendedor no tiene `ANULAR_VENTA` (`01` §19), así que la anulación la hace el supervisor
 * (`sup01`, con `ANULAR_VENTA` y `LIBERAR_UBICACION`: la camioneta está tomada por la jornada
 * del vendedor, VTA-21) desde `/admin`, sobre la venta a Kiosco La Esquina del criterio 6 (sin
 * cobro, ya enviada en el criterio 8):
 *   Cerveza B en la camioneta: 6 -> 18 latas (vuelven las 12 de la caja)
 *   saldo de Kiosco La Esquina: vuelve al de antes de esa venta
 * La venta no se borra: sigue en el listado, marcada como anulada, con su motivo.
 */
import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { abrirVista } from './apoyo/contextos'
import { expect, test } from './apoyo/fixtures'
import { exigir } from './apoyo/memoria'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 9 — anulación sin borrar historia', () => {
  test('el supervisor anula la venta desde /admin', async ({ browser, baseURL, vigilante }) => {
    const numero = exigir('numeroVenta6')
    const ventaId = (await new Consultas(await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'sup01')).ventas()).find(
      (v) => v.numero === numero,
    )?.venta_id
    expect(ventaId, `la venta ${numero} tiene que estar en el servidor (criterio 8)`).toBeDefined()

    const { page } = await abrirVista(browser, vigilante, 'PC', baseURL ?? '')
    await iniciarSesionEnAdmin(page, 'sup01')
    await page.goto(`/admin/ventas/${ventaId ?? ''}`)
    await page.getByRole('button', { name: 'Anular venta' }).click()
    await page.getByLabel('Motivo', { exact: true }).selectOption({ index: 1 })
    await page.getByRole('button', { name: 'Confirmar anulación' }).click()

    await expect(page.getByTestId('venta-anulada')).toBeVisible()
  })

  test('el stock y el saldo vuelven a su estado anterior y la venta sigue visible como anulada', async ({
    browser,
    baseURL,
  }) => {
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const consultas = new Consultas(api)

    // INV-19: la anulación devuelve el stock con movimientos inversos; no se borra nada.
    expect(await consultas.stockBase('Camioneta 1', 'CERV-B')).toBe(18)
    expect(await consultas.stockBase('Camioneta 1', 'VINO-A')).toBe(5)
    // El saldo de Kiosco La Esquina es el de antes de la venta anulada.
    expect(await consultas.saldoDeCliente('C002')).toBe(exigir('saldoC002Antes'))

    // INV-05: la venta anulada sigue en el listado (y la otra, confirmada).
    const ventas = await consultas.ventas()
    expect(ventas.find((v) => v.numero === exigir('numeroVenta6'))?.estado).toBe('ANULADA')
    expect(ventas.find((v) => v.numero === exigir('numeroVenta5'))?.estado).toBe('CONFIRMADA')
    const detalle = await api.leer<{ anulacion: { motivo?: string | null } | null }>(
      `/api/v1/ventas/${ventas.find((v) => v.numero === exigir('numeroVenta6'))?.venta_id ?? ''}`,
    )
    expect(detalle.anulacion).not.toBeNull()
  })
})
