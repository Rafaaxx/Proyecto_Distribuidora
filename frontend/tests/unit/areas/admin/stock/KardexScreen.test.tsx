import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { KardexScreen } from '../../../../../src/areas/admin/stock/KardexScreen'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const UBICACION = '11111111-1111-4111-8111-111111111111'
const PRODUCTO = '22222222-2222-4222-8222-222222222222'

function movimiento(id: string, cantidad: number, acumulado: number, costo?: string | null) {
  return {
    id,
    tipo: 'STOCK_INICIAL',
    cantidad_base: cantidad,
    origen_tipo: 'STOCK_INICIAL',
    origen_id: id,
    occurred_at: '2026-04-01T15:00:00Z',
    registered_at: '2026-04-01T15:00:00Z',
    usuario_id: id,
    operation_id: id,
    saldo_acumulado: acumulado,
    ...(costo !== undefined && { costo_unitario: costo }),
  }
}

function kardex(items: unknown[], cursor: string | null, extra: Record<string, unknown> = {}) {
  return {
    saldo_anterior: 0,
    saldo_actual: 48,
    zona_horaria: 'America/Argentina/Mendoza',
    producto_codigo: 'COD-1',
    producto_nombre: 'Vino A',
    unidades_referencia: 6,
    items,
    cursor_siguiente: cursor,
    ...extra,
  }
}

function renderKardex(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[`/admin/stock/ubicaciones/${UBICACION}/kardex/${PRODUCTO}`]}>
        <Routes>
          <Route path="/admin/stock/ubicaciones/:ubicacionId/kardex/:productoId" element={<KardexScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('KardexScreen (tarea 8.3, STK-04, D11)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un Administrador ve movimientos en cajas + unidades con costo y acumulado, y el saldo actual', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/kardex',
        responder: () => ({
          status: 200,
          cuerpo: kardex([movimiento('a', 60, 60, '1000.000000'), movimiento('b', -12, 48, '1000.000000')], null),
        }),
      },
    ])
    renderKardex('ADM')

    expect(await screen.findByText(/Vino A/)).toBeInTheDocument()
    const filas = screen.getAllByRole('row').slice(1)
    expect(within(filas[0] as HTMLElement).getByText('Stock inicial')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getAllByText('10 cajas')).toHaveLength(2) // cantidad y acumulado
    expect(within(filas[0] as HTMLElement).getByText('$ 1.000,000000')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('-2 cajas')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('8 cajas')).toBeInTheDocument() // acumulado 48
    expect(screen.getByText('Saldo actual: 8 cajas')).toBeInTheDocument()
    const [pedido] = llamadas(apiFetchMock, 'GET', '/stock/kardex')
    expect(pedido?.url.searchParams.get('producto_id')).toBe(PRODUCTO)
    expect(pedido?.url.searchParams.get('ubicacion_id')).toBe(UBICACION)
  })

  it('un Vendedor no ve la columna de costo', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/kardex',
        responder: () => ({ status: 200, cuerpo: kardex([movimiento('a', 60, 60)], null) }),
      },
    ])
    renderKardex('VEN')

    await screen.findByText(/Vino A/)
    expect(screen.queryByRole('columnheader', { name: 'Costo unitario' })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Saldo acumulado' })).toBeInTheDocument()
  })

  it('sin presentación de referencia muestra unidades', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/kardex',
        responder: () => ({
          status: 200,
          cuerpo: kardex([movimiento('a', 7, 7)], null, { unidades_referencia: null, saldo_actual: 7 }),
        }),
      },
    ])
    renderKardex('VEN')

    expect(await screen.findByText('Saldo actual: 7 un.')).toBeInTheDocument()
  })

  it('el período vuelve a pedir el kardex y muestra el saldo anterior', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/kardex',
        responder: (url) =>
          url.searchParams.has('desde')
            ? { status: 200, cuerpo: kardex([movimiento('b', 6, 66)], null, { saldo_anterior: 60 }) }
            : { status: 200, cuerpo: kardex([movimiento('a', 60, 60)], null) },
      },
    ])
    const usuario = userEvent.setup()
    renderKardex('ADM')
    await screen.findByText(/Vino A/)
    expect(screen.queryByText(/Saldo anterior/)).not.toBeInTheDocument()

    await usuario.type(screen.getByLabelText('Desde'), '2026-04-05')
    await usuario.type(screen.getByLabelText('Hasta'), '2026-04-10')
    await usuario.click(screen.getByRole('button', { name: 'Filtrar' }))

    expect(await screen.findByText('Saldo anterior: 10 cajas')).toBeInTheDocument()
    const consultas = llamadas(apiFetchMock, 'GET', '/stock/kardex')
    const ultima = consultas[consultas.length - 1]
    expect(ultima?.url.searchParams.get('desde')).toBe('2026-04-05')
    expect(ultima?.url.searchParams.get('hasta')).toBe('2026-04-10')
  })

  it('un rango invertido no se envía', async () => {
    enrutar(apiFetchMock, [
      { ruta: '/stock/kardex', responder: () => ({ status: 200, cuerpo: kardex([], null) }) },
    ])
    const usuario = userEvent.setup()
    renderKardex('ADM')
    await screen.findByText(/Vino A/)
    const antes = apiFetchMock.mock.calls.length

    await usuario.type(screen.getByLabelText('Desde'), '2026-04-10')
    await usuario.type(screen.getByLabelText('Hasta'), '2026-04-01')
    await usuario.click(screen.getByRole('button', { name: 'Filtrar' }))

    expect(await screen.findByText('"Desde" no puede ser posterior a "Hasta".')).toBeInTheDocument()
    expect(apiFetchMock.mock.calls.length).toBe(antes)
  })

  it('"Cargar más" continúa el acumulado con el cursor', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/kardex',
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: kardex([movimiento('b', 6, 66)], null) }
            : { status: 200, cuerpo: kardex([movimiento('a', 60, 60)], 'c1') },
      },
    ])
    const usuario = userEvent.setup()
    renderKardex('ADM')

    await usuario.click(await screen.findByRole('button', { name: 'Cargar más' }))

    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(3))
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
  })

  it('sin movimientos en el período lo dice', async () => {
    enrutar(apiFetchMock, [
      { ruta: '/stock/kardex', responder: () => ({ status: 200, cuerpo: kardex([], null) }) },
    ])
    renderKardex('ADM')

    expect(await screen.findByText('No hay movimientos en este período.')).toBeInTheDocument()
  })

  it('un producto o una ubicación ajena (404) lo avisa', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/kardex',
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
    ])
    renderKardex('ADM')

    expect(await screen.findByRole('alert')).toHaveTextContent('El producto o la ubicación pedidos no existen.')
  })

  it('sin TRANSFERIR_STOCK no se monta ni se pide nada', async () => {
    renderKardex('CON')

    expect(await screen.findByText('No tenés permiso para ver el stock.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
