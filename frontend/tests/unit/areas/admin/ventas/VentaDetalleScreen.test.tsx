import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VentaDetalleScreen } from '../../../../../src/areas/admin/ventas/VentaDetalleScreen'
import type { ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import {
  COBRANZA_ID,
  JORNADA_ID,
  LINEA_BOTELLAS,
  LINEA_CAJAS,
  MOTIVO_LISTA_ID,
  VENTA_ID,
  montarApi,
  ventaDetalle,
} from './ventasDePrueba'

function renderPantalla(rol: RolDePrueba = 'SUP', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/ventas/${VENTA_ID}`]}>
        <Routes>
          <Route path="/admin/ventas/:ventaId" element={<VentaDetalleScreen />} />
          <Route path="/admin/ventas" element={<p>Listado de ventas</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function detalle(campos: Partial<Record<string, unknown>> = {}): ReglaDeApi {
  return { metodo: 'GET', ruta: `/ventas/${VENTA_ID}`, responder: () => ({ status: 200, cuerpo: ventaDetalle(campos) }) }
}

const LINEA_CON_COSTO = { ...LINEA_CAJAS, costo_unitario: '1050.000000', costo_total: '75600.00' }

describe('VentaDetalleScreen (tarea 12.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra la venta como quedó congelada: cabecera, líneas en su presentación, totales y cobranza enlazada', async () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla('SUP')

    expect(await screen.findByRole('heading', { name: /venta v01-000042/i })).toBeInTheDocument()
    const cabecera = screen.getByTestId('cabecera-de-la-venta')
    expect(cabecera).toHaveTextContent('Kiosco La Esquina')
    expect(cabecera).toHaveTextContent('Juan Vendedor')
    expect(cabecera).toHaveTextContent('Depósito central')
    expect(cabecera).toHaveTextContent('Confirmada')
    expect(cabecera).toHaveTextContent('Con conexión')
    expect(cabecera).toHaveTextContent('Jornada: sin jornada')

    const caja = screen.getByTestId('linea-l1')
    expect(caja).toHaveTextContent('Vino A')
    expect(caja).toHaveTextContent('2 × Caja x6 (12 unidades)')
    expect(caja).toHaveTextContent('$ 25.000,00')
    const botellas = screen.getByTestId('linea-l2')
    expect(botellas).toHaveTextContent('3 × Botella (3 unidades)')
    expect(botellas).toHaveTextContent('$ 6.250,00')

    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 31.250,00')
    const cobranza = screen.getByTestId('cobranza-de-la-venta')
    expect(cobranza).toHaveTextContent('$ 20.000,00')
    expect(within(cobranza).getByRole('link', { name: /ver la cobranza/i })).toHaveAttribute('href', `/admin/cobranzas/${COBRANZA_ID}`)
  })

  it('muestra la lista y la versión; con otra lista elegida, también el motivo (PRC-21, PRC-23)', async () => {
    montarApi(apiFetchMock, [detalle()])
    const primero = renderPantalla('SUP')
    const lista = await screen.findByTestId('lista-de-la-venta')
    expect(lista).toHaveTextContent('Mayorista')
    expect(lista).toHaveTextContent('Versión 2')
    expect(lista).not.toHaveTextContent(/motivo/i)
    primero.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [detalle({ motivo_lista: { motivo_id: MOTIVO_LISTA_ID, nombre: 'Precio acordado con el cliente' } })])
    renderPantalla('SUP')
    expect(await screen.findByTestId('lista-de-la-venta')).toHaveTextContent('Motivo: Precio acordado con el cliente')
  })

  it('una venta con jornada enlaza al listado de esa jornada; una sin cobranza lo dice', async () => {
    montarApi(apiFetchMock, [detalle({ jornada_id: JORNADA_ID, cobranza: null })])
    renderPantalla('SUP')

    expect(await screen.findByRole('link', { name: /ventas de esta jornada/i })).toHaveAttribute('href', `/admin/ventas?jornada=${JORNADA_ID}`)
    expect(screen.getByTestId('cobranza-de-la-venta')).toHaveTextContent(/sin cobranza en el acto/i)
  })

  // Escenario: "Venta con observaciones"
  it('la marca "Stock negativo" aparece junto a su línea con el saldo resultante (SYN-07, STK-05)', async () => {
    montarApi(apiFetchMock, [
      detalle({
        observaciones: [
          { codigo: 'STOCK_NEGATIVO', estado: 'PENDIENTE', detalle: { linea_id: 'l1', producto_id: 'x', saldo_resultante: -4 } },
          { codigo: 'CONSUMIDOR_FINAL_CON_DEUDA', estado: 'PENDIENTE', detalle: { total: '4300.00', cobranza: '4000.00' } },
        ],
      }),
    ])
    renderPantalla('SUP')

    const linea = await screen.findByTestId('linea-l1')
    expect(linea).toHaveTextContent('Stock negativo')
    expect(linea).toHaveTextContent('Saldo resultante: -4 unidades')
    expect(screen.getByTestId('linea-l2')).not.toHaveTextContent('Stock negativo')
    expect(screen.getByTestId('observaciones-generales')).toHaveTextContent('Consumidor final con deuda')
    expect(screen.getByTestId('observaciones-generales')).toHaveTextContent('Total $ 4.300,00 · cobrado $ 4.000,00')
  })

  // Escenarios: "Detalle sin costos" / "Detalle con costos"
  it('con VER_COSTOS muestra costo unitario y total de cada línea (VTA-05)', async () => {
    montarApi(apiFetchMock, [detalle({ lineas: [LINEA_CON_COSTO, LINEA_BOTELLAS] })])
    renderPantalla('ADM')

    const linea = await screen.findByTestId('linea-l1')
    expect(linea).toHaveTextContent('Costo unitario: 1.050,000000')
    expect(linea).toHaveTextContent('Costo total: $ 75.600,00')
    expect(screen.getByTestId('linea-l2')).toHaveTextContent('Sin costo informado')
  })

  it('sin VER_COSTOS no muestra ninguna señal de costo (nulos de la API) ni utilidad', async () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla('SUP')

    await screen.findByTestId('linea-l1')
    expect(screen.queryByText(/costo/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/utilidad/i)).not.toBeInTheDocument()
  })

  it('sin permiso de leer cobranzas la cobranza se muestra sin enlace', async () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla('SUP', ['VENDER'])

    const cobranza = await screen.findByTestId('cobranza-de-la-venta')
    expect(cobranza).toHaveTextContent('$ 20.000,00')
    expect(within(cobranza).queryByRole('link')).not.toBeInTheDocument()
  })

  it('una venta que no existe o es de otra organización muestra el aviso (404, INV-21)', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/ventas/${VENTA_ID}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
    renderPantalla('SUP')
    expect(await screen.findByText(/no se encontr[oó] la venta/i)).toBeInTheDocument()
  })

  it('un error cualquiera y un 403 se muestran sin romper la pantalla', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: `/ventas/${VENTA_ID}`, responder: () => ({ status: 500, cuerpo: { title: 'Falla', codigo: 'ERROR' } }) }])
    const primero = renderPantalla('SUP')
    expect(await screen.findByText(/no se pudo obtener la venta/i)).toBeInTheDocument()
    primero.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: `/ventas/${VENTA_ID}`, responder: () => ({ status: 403, cuerpo: { title: 'No', codigo: 'PERMISO_REQUERIDO' } }) }])
    renderPantalla('SUP')
    expect(await screen.findByText(/no ten[eé]s permiso para ver las ventas/i)).toBeInTheDocument()
  })

  it('sin VENDER ni ANULAR_VENTA no pide nada', () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla('CON')
    expect(screen.getByText(/no ten[eé]s permiso para ver las ventas/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
