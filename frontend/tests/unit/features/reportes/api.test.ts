import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import {
  obtenerDetalleDeRendicion,
  obtenerReporteDeAjustes,
  obtenerReporteDeObservaciones,
  obtenerReporteDeRendiciones,
  obtenerReporteDeSaldosDeClientes,
  obtenerReporteDeSaldosDeProveedores,
  obtenerReporteDeVentas,
} from '../../../../src/features/reportes/api'
import { ErrorDeReportes, RecursoNoEncontradoReportesError } from '../../../../src/features/reportes/errores'

/**
 * Change 26, tarea 9.1 (D1, D3): el pedido del reporte de ventas manda solo los filtros elegidos (sin fechas, el
 * servidor usa el mes en curso) y traduce el error por su código estable.
 */
describe('obtenerReporteDeVentas', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('sin filtros pide /reportes/ventas sin parámetros (el servidor elige el mes en curso)', async () => {
    apiFetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ ve_utilidad: true }) })

    const reporte = await obtenerReporteDeVentas({})

    expect(apiFetchMock).toHaveBeenCalledWith('/reportes/ventas')
    expect(reporte.ve_utilidad).toBe(true)
  })

  it('manda desde, hasta y vendedor solo cuando están elegidos', async () => {
    apiFetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })

    await obtenerReporteDeVentas({ desde: '2026-10-01', hasta: '2026-10-31', vendedorId: 'abc' })
    await obtenerReporteDeVentas({ hasta: '2026-10-31' })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/reportes/ventas?desde=2026-10-01&hasta=2026-10-31&vendedor_id=abc')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/reportes/ventas?hasta=2026-10-31')
  })

  it('un 422 lanza el error de dominio con su código', async () => {
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ title: 'x', codigo: 'RANGO_DE_FECHAS_INVALIDO' }),
    })

    await expect(obtenerReporteDeVentas({ desde: '2026-11-10', hasta: '2026-11-01' })).rejects.toMatchObject({
      codigo: 'RANGO_DE_FECHAS_INVALIDO',
    })
    await expect(obtenerReporteDeVentas({})).rejects.toBeInstanceOf(ErrorDeReportes)
  })
})

/**
 * Change 26, tarea 11.1, 12.1 a 12.3 (D7 a D10): los pedidos de los demás reportes mandan solo los filtros
 * elegidos, con los nombres de parámetro del servidor.
 */
describe('los demás reportes (D7 a D10)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })
  })

  it('rendiciones: período, vendedor y estado solo si están elegidos', async () => {
    await obtenerReporteDeRendiciones({})
    await obtenerReporteDeRendiciones({ desde: '2026-11-01', vendedorId: 'v1', estado: 'CERRADA' })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/reportes/rendiciones')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/reportes/rendiciones?desde=2026-11-01&vendedor_id=v1&estado=CERRADA')
  })

  it('el detalle de una jornada pide /reportes/rendiciones/{id} y un 404 es «no encontrada»', async () => {
    await obtenerDetalleDeRendicion('j-1')
    expect(apiFetchMock).toHaveBeenCalledWith('/reportes/rendiciones/j-1')

    apiFetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({ title: 'x', codigo: 'RECURSO_NO_ENCONTRADO' }) })
    await expect(obtenerDetalleDeRendicion('j-2')).rejects.toBeInstanceOf(RecursoNoEncontradoReportesError)
  })

  it('observaciones y ajustes: solo el período', async () => {
    await obtenerReporteDeObservaciones({ desde: '2026-10-01', hasta: '2026-10-31' })
    await obtenerReporteDeAjustes({})

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/reportes/observaciones?desde=2026-10-01&hasta=2026-10-31')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/reportes/ajustes')
  })

  it('saldos de clientes: saldo, vendedor, estado y búsqueda; sin filtros no manda nada', async () => {
    await obtenerReporteDeSaldosDeClientes({})
    await obtenerReporteDeSaldosDeClientes({ saldo: 'DEUDORES', vendedorId: 'v1', estado: 'ACTIVO', texto: 'Perez Hnos' })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/reportes/saldos/clientes')
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/reportes/saldos/clientes?saldo=DEUDORES&vendedor_id=v1&estado=ACTIVO&texto=Perez+Hnos',
    )
  })

  it('saldos de proveedores: saldo, estado y búsqueda (sin vendedor)', async () => {
    await obtenerReporteDeSaldosDeProveedores({ saldo: 'A_FAVOR', texto: 'Bodega' })

    expect(apiFetchMock).toHaveBeenCalledWith('/reportes/saldos/proveedores?saldo=A_FAVOR&texto=Bodega')
  })

  it('un 403 de los saldos de proveedores lanza el error de permiso', async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 403, json: async () => ({ title: 'Sin permiso', codigo: 'PERMISO_REQUERIDO' }) })

    await expect(obtenerReporteDeSaldosDeProveedores({})).rejects.toMatchObject({ codigo: 'PERMISO_REQUERIDO' })
  })
})

/**
 * Change 26, tarea 21.8 (D14): la página solo viaja desde la segunda (sin ella el servidor trae la primera) y cada
 * lista del reporte de ventas tiene su propio parámetro.
 */
describe('páginas de las listas (D14)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })
  })

  it('ventas: cada lista manda su parámetro desde la página 2 y la página 1 no viaja', async () => {
    await obtenerReporteDeVentas({ paginaPorDia: 1, paginaPorProducto: 1, paginaAnuladas: 1 })
    await obtenerReporteDeVentas({ paginaPorDia: 3 })
    await obtenerReporteDeVentas({ vendedorId: 'v1', paginaPorProducto: 2, paginaAnuladas: 4 })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/reportes/ventas')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/reportes/ventas?pagina_por_dia=3')
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      3,
      '/reportes/ventas?vendedor_id=v1&pagina_por_producto=2&pagina_anuladas=4',
    )
  })

  it('rendiciones y saldos mandan `pagina` desde la 2', async () => {
    await obtenerReporteDeRendiciones({ pagina: 1 })
    await obtenerReporteDeRendiciones({ estado: 'CERRADA', pagina: 2 })
    await obtenerReporteDeSaldosDeClientes({ pagina: 3 })
    await obtenerReporteDeSaldosDeProveedores({ saldo: 'TODOS', pagina: 2 })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/reportes/rendiciones')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/reportes/rendiciones?estado=CERRADA&pagina=2')
    expect(apiFetchMock).toHaveBeenNthCalledWith(3, '/reportes/saldos/clientes?pagina=3')
    expect(apiFetchMock).toHaveBeenNthCalledWith(4, '/reportes/saldos/proveedores?saldo=TODOS&pagina=2')
  })
})
