/**
 * Change 16b, tarea 4.1: ayuda contextual en las pantallas de descuentos (spec `ayuda-contextual`,
 * requisito "Las pantallas de descuentos explican sus reglas"; DSC-03, DSC-05, DSC-06; ADR-050,
 * ADR-051). Solo se prueba que los "(?)" existan, abran su texto y no cambien lo cargado.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import DescuentosArea from '../../../../../src/areas/admin/descuentos/DescuentosArea'
import { enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { REGLA_ID, ROLES, regla, reglasDeCatalogo } from './descuentosDePrueba'

function montar(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/descuentos/*" element={<DescuentosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function botonDeAyuda(titulo: string) {
  return screen.getByRole('button', { name: `Ayuda: ${titulo}` })
}

beforeEach(() => {
  apiFetchMock.mockReset()
  Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  enrutar(apiFetchMock, [
    ...reglasDeCatalogo(),
    { metodo: 'GET', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla() }) },
    { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: ROLES }) },
  ])
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('ayuda en el formulario de regla', () => {
  it.each([
    ['Alcance de la regla', /cuenta y descuenta todo lo vendido/],
    ['Medida', /15 botellas de un vino que viene x6 = 2,5 cajas/],
    ['Umbral', /en unidades, solo enteros \(60\)/],
    ['Acción', /\$879,04 y \$120,96/],
    ['Prioridad', /no la de prioridad 1/],
    ['Acumulable', /8 % y después 2 % dan 9,84 %, no 10 %/],
    ['Vigencia', /todo noviembre/],
  ])('"(?)" de %s abre su texto', async (titulo, texto) => {
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await usuario.click(botonDeAyuda(titulo))

    expect(screen.getByText(texto)).toBeVisible()
  })

  it('no hay "(?)" de Operador (se eliminó: se entiende sola)', () => {
    montar('/admin/descuentos/nueva')

    expect(screen.queryByRole('button', { name: /ayuda: operador/i })).not.toBeInTheDocument()
  })

  it('abrir uno no cambia lo cargado ni envía el formulario', async () => {
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')
    await usuario.type(screen.getByLabelText(/^nombre$/i), 'Mayorista')
    await usuario.type(screen.getByLabelText(/^umbral$/i), '20')

    await usuario.click(botonDeAyuda('Medida'))
    await usuario.keyboard('{Escape}')

    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('Mayorista')
    expect(screen.getByLabelText(/^umbral$/i)).toHaveValue('20')
    expect(apiFetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')).toHaveLength(0)
  })

  it('el "Ver más" de Acumulable lleva a "Cómo se aplican los descuentos" en otra pestaña', async () => {
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await usuario.click(botonDeAyuda('Acumulable'))

    const enlace = screen.getByRole('link', { name: /ver más/i })
    expect(enlace).toHaveAttribute('href', '/admin/ayuda/descuentos')
    expect(enlace).toHaveAttribute('target', '_blank')
  })
})

describe('ayuda en el detalle de la regla', () => {
  it('un borrador muestra el "(?)" junto a "Activar"', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/descuentos/${REGLA_ID}`)
    await screen.findByRole('button', { name: 'Activar' })

    await usuario.click(botonDeAyuda('Activar'))

    expect(screen.getByText(/solo se puede editar mientras es borrador/i)).toBeVisible()
  })
})

describe('ayuda en "Topes por rol"', () => {
  it('el diálogo de tope ofrece el "(?)" de "Tope de descuento" con "Ver más" a topes', async () => {
    const usuario = userEvent.setup()
    montar('/admin/descuentos/topes')
    const fila = (await screen.findByText('Vendedor/Repartidor')).closest('tr') as HTMLElement
    await usuario.click(within(fila).getByRole('button', { name: /definir tope/i }))

    await usuario.click(botonDeAyuda('Tope de descuento'))

    expect(screen.getByText(/autorización, que vale para toda la venta/)).toBeVisible()
    expect(screen.getByRole('link', { name: /ver más/i })).toHaveAttribute('href', '/admin/ayuda/topes')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
