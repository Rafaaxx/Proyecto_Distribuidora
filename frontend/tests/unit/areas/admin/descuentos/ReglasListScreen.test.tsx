/**
 * Change 16, tarea 15.2: listado de reglas de descuento (spec `administracion-de-descuentos`,
 * requisito "Las reglas se cargan y se revisan desde la pantalla"; DSC-01, DSC-03).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import DescuentosArea from '../../../../../src/areas/admin/descuentos/DescuentosArea'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { regla, reglaDeMarca } from './descuentosDePrueba'

function montar() {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={['/admin/descuentos']}>
        <Routes>
          <Route path="/admin/descuentos/*" element={<DescuentosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('listado de reglas de descuento (tarea 15.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('Escenario descripción legible: "Cajas equivalentes ≥ 20 → 5 %" con prioridad, estado y "No acumulable"', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 200, cuerpo: { items: [regla()], siguiente_cursor: null } }) },
    ])
    montar()

    const fila = (await screen.findByText('Cajas equivalentes ≥ 20 → 5 %')).closest('tr') as HTMLElement
    expect(within(fila).getByText('Mayorista 20 cajas')).toBeInTheDocument()
    expect(within(fila).getByText('Prioridad 10')).toBeInTheDocument()
    expect(within(fila).getByText('Borrador')).toBeInTheDocument()
    expect(within(fila).getByText('No acumulable')).toBeInTheDocument()
    expect(within(fila).getByText('Sobre toda la venta')).toBeInTheDocument()
    expect(within(fila).getByText('Sin vigencia definida')).toBeInTheDocument()
  })

  it('una regla de alcance con importe fijo, acumulable, muestra su alcance y su acción', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 200, cuerpo: { items: [reglaDeMarca()], siguiente_cursor: null } }) },
    ])
    montar()

    const fila = (await screen.findByText('Importe bruto ≥ $ 100.000,00 → $ 5.000,00 fijos')).closest('tr') as HTMLElement
    expect(within(fila).getByText('Sobre Marca Coca-Cola')).toBeInTheDocument()
    expect(within(fila).getByText('Acumulable')).toBeInTheDocument()
    expect(within(fila).getByText('Activa')).toBeInTheDocument()
  })

  it('el nombre de cada regla lleva a su detalle', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 200, cuerpo: { items: [regla()], siguiente_cursor: null } }) },
    ])
    montar()

    expect(await screen.findByRole('link', { name: 'Mayorista 20 cajas' })).toHaveAttribute(
      'href',
      '/admin/descuentos/11111111-1111-4111-8111-111111111111',
    )
  })

  it('una regla vencida se ve "Vencida" y el filtro de estado pide al servidor ese estado', async () => {
    enrutar(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/descuentos/reglas',
        responder: (url) => ({
          status: 200,
          cuerpo: {
            items: url.searchParams.get('estado') === 'VENCIDA' ? [reglaDeMarca({ estado: 'VENCIDA', vigencia_hasta: '2026-09-01T12:00:00Z' })] : [regla()],
            siguiente_cursor: null,
          },
        }),
      },
    ])
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Mayorista 20 cajas')

    await usuario.selectOptions(screen.getByLabelText(/^estado$/i), 'VENCIDA')

    expect(await screen.findByText('Coca-Cola importe fijo')).toBeInTheDocument()
    expect(screen.getByText('Vencida', { selector: 'span' })).toBeInTheDocument()
    expect(screen.queryByText('Mayorista 20 cajas')).not.toBeInTheDocument()
    const pedidos = llamadas(apiFetchMock, 'GET', '/descuentos/reglas')
    expect(pedidos[0]?.url.searchParams.has('estado')).toBe(false)
    expect(pedidos.at(-1)?.url.searchParams.get('estado')).toBe('VENCIDA')
  })

  it('el filtro ofrece los cuatro estados', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 200, cuerpo: { items: [], siguiente_cursor: null } }) },
    ])
    montar()

    const filtro = await screen.findByLabelText(/^estado$/i)

    expect(within(filtro).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Todos los estados',
      'Borrador',
      'Activa',
      'Pausada',
      'Vencida',
    ])
  })

  it('sin reglas lo dice, y "Nueva regla" lleva al alta', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 200, cuerpo: { items: [], siguiente_cursor: null } }) },
    ])
    montar()

    expect(await screen.findByText(/todavía no hay reglas de descuento/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /nueva regla/i })).toHaveAttribute('href', '/admin/descuentos/nueva')
  })

  it('"Cargar más" pide la página siguiente con el cursor', async () => {
    enrutar(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/descuentos/reglas',
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: { items: [reglaDeMarca()], siguiente_cursor: null } }
            : { status: 200, cuerpo: { items: [regla()], siguiente_cursor: 'c1' } },
      },
    ])
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Mayorista 20 cajas')

    await usuario.click(screen.getByRole('button', { name: /cargar más/i }))

    expect(await screen.findByText('Coca-Cola importe fijo')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cargar más/i })).not.toBeInTheDocument()
  })

  it('si falla la lectura, lo avisa', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 500, cuerpo: { title: 'Error', codigo: 'ERROR_INTERNO' } }) },
    ])
    montar()

    expect(await screen.findByText(/no se pudieron obtener las reglas de descuento/i)).toBeInTheDocument()
  })
})
