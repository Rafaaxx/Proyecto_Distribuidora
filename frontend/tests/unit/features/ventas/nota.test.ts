/**
 * Adaptador de la API a los datos neutros de la nota y hook `useNotaDeVenta` (change 20, tarea
 * 7.1; VTA-13, VTA-03, VTA-04, INV-03, INV-14, ADR-008, ADR-059; D14). Las respuestas de los modos
 * B y C son fabricadas: la confirmación las rechaza hasta la etapa 4.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { armarNotaDeVenta, NotaNoDisponibleParaModoC } from '../../../../src/domain/ventas/notaDeVenta'
import type { NotaDeVenta } from '../../../../src/features/ventas/api'
import { useNotaDeVenta } from '../../../../src/features/ventas/hooks'
import { datosDeNotaDesdeApi } from '../../../../src/features/ventas/nota'
import { enrutar } from '../../utils/enrutarApi'

const VENTA_ID = '77777777-7777-4777-8777-777777777777'

function respuesta(sobre: Partial<NotaDeVenta> = {}): NotaDeVenta {
  return {
    organizacion: { nombre: 'Distribuidora Norte', cuit: '30-12345678-9', domicilio: 'Av. Siempreviva 742', telefono: null },
    zona_horaria: 'America/Argentina/Mendoza',
    muestra_saldo: true,
    cliente: {
      nombre: 'Kiosco La Esquina',
      razon_social: 'La Esquina SRL',
      documento_tipo: 'CUIT',
      documento_numero: '30-98765432-1',
      direccion: 'San Martín 100',
      es_consumidor_final: false,
    },
    numero: 'V03-000142',
    occurred_at: '2026-10-20T15:30:00Z',
    vendedor_nombre: 'Vendedor Uno',
    modo_impositivo: 'A',
    estado: 'CONFIRMADA',
    lineas: [
      {
        orden: 0,
        producto_nombre: 'Gaseosa Cola 1,5 L',
        presentacion_nombre: 'Caja x12',
        cantidad: 2,
        unidades_presentacion: 12,
        precio_referencia: '100.10',
        unidades_referencia: 1,
        importe_bruto: '2402.40',
        importe_descuento: '0.00',
        importe_neto: '2402.40',
        alicuota: '0.210000',
        importe_iva: '0.00',
      },
    ],
    total_neto: '2402.40',
    total_iva: '0.00',
    total: '2402.40',
    cobranza: { importe: '1000.00', estado: 'CONFIRMADA', medios: [{ nombre: 'Efectivo', importe: '1000.00' }] },
    saldo_resultante: '210000.55',
    anulacion: null,
    ...sobre,
  }
}

describe('datosDeNotaDesdeApi (7.1)', () => {
  it('conserva los importes como texto, sin perder decimales (INV-03), y el modo, la alícuota y el IVA de cada línea', () => {
    const datos = datosDeNotaDesdeApi(respuesta({ total: '2402.40', saldo_resultante: '210000.55' }))

    expect(datos.total).toBe('2402.40')
    expect(datos.saldo_resultante).toBe('210000.55')
    expect(datos.lineas[0]).toMatchObject({ precio_referencia: '100.10', alicuota: '0.210000', importe_iva: '0.00' })
    expect(datos.modo_impositivo).toBe('A')
    expect(datos.cobranza).toEqual({ importe: '1000.00', medios: [{ nombre: 'Efectivo', importe: '1000.00' }] })
    expect(datos.muestra_saldo).toBe(true)
    expect(datos.organizacion.telefono).toBeNull()
  })

  it('una venta de modo B fabricada conserva el IVA congelado de cada línea (VTA-04)', () => {
    const linea = respuesta().lineas[0]!
    const datos = datosDeNotaDesdeApi(
      respuesta({
        modo_impositivo: 'B',
        lineas: [
          { ...linea, importe_neto: '10000.00', alicuota: '0.210000', importe_iva: '2100.00' },
          { ...linea, orden: 1, importe_neto: '2000.00', alicuota: '0.105000', importe_iva: '210.00' },
        ],
        total_neto: '12000.00',
        total_iva: '2310.00',
        total: '14310.00',
      }),
    )

    expect(datos.modo_impositivo).toBe('B')
    expect(datos.lineas.map((l) => [l.alicuota, l.importe_iva])).toEqual([
      ['0.210000', '2100.00'],
      ['0.105000', '210.00'],
    ])
    expect(datos.total_neto).toBe('12000.00')
    expect(datos.total_iva).toBe('2310.00')
  })

  it('una venta de modo C se convierte sin error: el rechazo es del armado (D14)', () => {
    const datos = datosDeNotaDesdeApi(respuesta({ modo_impositivo: 'C' }))

    expect(datos.modo_impositivo).toBe('C')
    expect(() => armarNotaDeVenta(datos)).toThrow(NotaNoDisponibleParaModoC)
  })

  it('el consumidor final sin dirección y los nombres nulos usan los valores neutros', () => {
    const base = respuesta()
    const datos = datosDeNotaDesdeApi(
      respuesta({
        cliente: { ...base.cliente, es_consumidor_final: true, direccion: '', razon_social: null, documento_tipo: null, documento_numero: null },
        vendedor_nombre: null,
        lineas: [{ ...base.lineas[0]!, producto_nombre: null }],
        anulacion: { anulada_en: '2026-10-21T10:00:00Z', motivo_nombre: null, devuelve_dinero: null },
      }),
    )

    expect(datos.cliente.direccion).toBeNull()
    expect(datos.vendedor_nombre).toBe('—')
    expect(datos.lineas[0]!.producto_nombre).toBe('—')
    expect(datos.anulacion).toEqual({ anulada_en: '2026-10-21T10:00:00Z', motivo_nombre: '—', devuelve_dinero: false })
  })
})

function envoltura() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: cliente }, children)
}

function servirNota(cuerpo: unknown, status = 200) {
  enrutar(apiFetchMock, [{ metodo: 'GET', ruta: `/ventas/${VENTA_ID}/nota`, responder: () => ({ status, cuerpo }) }])
}

describe('useNotaDeVenta (7.1)', () => {
  beforeEach(() => apiFetchMock.mockReset())
  afterEach(() => vi.clearAllMocks())

  it('lee la nota y expone el número y si está anulada', async () => {
    servirNota(respuesta())
    const { result } = renderHook(() => useNotaDeVenta(VENTA_ID), { wrapper: envoltura() })

    expect(result.current.estado).toBe('cargando')
    await waitFor(() => expect(result.current.estado).toBe('lista'))
    expect(result.current.estado === 'lista' && result.current.numero).toBe('V03-000142')
    expect(result.current.estado === 'lista' && result.current.anulada).toBe(false)
  })

  it('una venta de modo C expone "no disponible" y no un error genérico (D14)', async () => {
    servirNota(respuesta({ modo_impositivo: 'C' }))
    const { result } = renderHook(() => useNotaDeVenta(VENTA_ID), { wrapper: envoltura() })

    await waitFor(() => expect(result.current.estado).toBe('no-disponible'))
  })

  it('un error de lectura expone "error" con reintentar que vuelve a pedir la nota', async () => {
    servirNota({ title: 'Falla', codigo: 'ERROR' }, 500)
    const { result } = renderHook(() => useNotaDeVenta(VENTA_ID), { wrapper: envoltura() })
    await waitFor(() => expect(result.current.estado).toBe('error'))

    servirNota(respuesta())
    if (result.current.estado === 'error') result.current.reintentar()
    await waitFor(() => expect(result.current.estado).toBe('lista'))
  })

  it('una venta anulada se marca como anulada', async () => {
    servirNota(
      respuesta({ estado: 'ANULADA', anulacion: { anulada_en: '2026-10-21T10:00:00Z', motivo_nombre: 'Error de carga', devuelve_dinero: true } }),
    )
    const { result } = renderHook(() => useNotaDeVenta(VENTA_ID), { wrapper: envoltura() })

    await waitFor(() => expect(result.current.estado).toBe('lista'))
    expect(result.current.estado === 'lista' && result.current.anulada).toBe(true)
  })

  it('no pide nada si no está habilitado', () => {
    servirNota(respuesta())
    renderHook(() => useNotaDeVenta(VENTA_ID, false), { wrapper: envoltura() })

    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
