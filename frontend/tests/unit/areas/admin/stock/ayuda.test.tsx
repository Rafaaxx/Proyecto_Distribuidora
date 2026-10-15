/**
 * Change 16b, tarea 5.3: ayuda contextual en stock y jornadas (spec `ayuda-contextual`,
 * requisito "Las pantallas de stock y jornadas explican la toma de ubicación"; STK-09, RUT-09,
 * ADR-051).
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import StockArea from '../../../../../src/areas/admin/stock/StockArea'
import { enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const CAMIONETA = '22222222-2222-4222-8222-222222222221'
const JORNADA = '33333333-3333-4333-8333-333333333333'
const JUAN = '44444444-4444-4444-8444-444444444444'
const DISPOSITIVO = '55555555-5555-4555-8555-555555555555'

const UBICACIONES = {
  items: [
    {
      id: CAMIONETA,
      nombre: 'Camioneta 1',
      tipo: 'VEHICULO',
      requiere_toma: true,
      activo: true,
      actualizado_en: '2026-01-01T00:00:00Z',
      jornada: { id: JORNADA, usuario_id: JUAN, usuario_nombre: 'Juan', abierta_en: '2026-04-10T11:00:00Z', estado: 'ABIERTA' },
    },
  ],
  cursor_siguiente: null,
}

const DETALLE = {
  id: JORNADA,
  ubicacion_id: CAMIONETA,
  ubicacion_nombre: 'Camioneta 1',
  usuario_id: JUAN,
  usuario_nombre: 'Juan',
  dispositivo_id: DISPOSITIVO,
  estado: 'ABIERTA',
  abierta_en: '2026-04-10T11:00:00Z',
  rendida_en: null,
  rendida_por_id: null,
  rendida_por_nombre: null,
  cerrada_en: null,
  cerrada_por_id: null,
  cerrada_por_nombre: null,
  liberada_en: null,
  liberada_por_id: null,
  liberada_por_nombre: null,
  motivo_liberacion_id: null,
  motivo_liberacion_nombre: null,
  observacion_liberacion: null,
}

function montar(ruta: string, rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/stock/*" element={<StockArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function ayuda(titulo: string) {
  return screen.getByRole('button', { name: `Ayuda: ${titulo}` })
}

beforeEach(() => {
  apiFetchMock.mockReset()
  enrutar(apiFetchMock, [
    { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
    { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: DETALLE }) },
    { ruta: '/stock/jornadas/actual', responder: () => ({ status: 404, cuerpo: { title: 'No hay', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    { ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: { items: [] } }) },
  ])
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('ayuda de la toma de ubicación', () => {
  it('el formulario de ubicación explica "Requiere toma"', async () => {
    const usuario = userEvent.setup()
    montar('/admin/stock/ubicaciones/nueva')
    await screen.findByText(/^requiere toma$/i)

    await usuario.click(ayuda('Requiere toma'))

    expect(screen.getByText(/Los vehículos siempre la requieren/)).toBeVisible()
  })

  it('el "(?)" no cuelga del label de la casilla: marcarla sigue funcionando y abrir la ayuda no la cambia', async () => {
    const usuario = userEvent.setup()
    montar('/admin/stock/ubicaciones/nueva')
    const casilla = await screen.findByRole('checkbox', { name: /^requiere toma$/i })

    await usuario.click(ayuda('Requiere toma'))

    expect(casilla).not.toBeChecked()
  })

  it('el listado explica "Toma actual" en el encabezado de la columna', async () => {
    const usuario = userEvent.setup()
    montar('/admin/stock')
    await screen.findByText('Camioneta 1')

    await usuario.click(ayuda('Toma actual'))

    expect(screen.getByText(/cuando pasa a rendición, ya nadie puede/i)).toBeVisible()
  })

  it('la apertura de jornada explica la toma actual', async () => {
    const usuario = userEvent.setup()
    montar('/admin/stock/jornadas/abrir', 'VEN')
    await screen.findByRole('button', { name: /abrir jornada/i })

    await usuario.click(ayuda('Toma actual'))

    expect(screen.getByText(/solo ese vendedor/)).toBeVisible()
  })

  it('el detalle de jornada ofrece "Liberar" con su "(?)" solo donde se ve "Liberar"', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/stock/jornadas/${JORNADA}`, 'SUP')
    await screen.findByRole('button', { name: 'Liberar' })

    await usuario.click(ayuda('Liberar ubicación'))

    expect(screen.getByText(/se le rompió el teléfono al vendedor/)).toBeVisible()
  })

  it('sin permiso de liberar (Vendedor) no hay "Liberar" ni su "(?)"', async () => {
    montar(`/admin/stock/jornadas/${JORNADA}`, 'VEN')
    await screen.findByText('Abierta', { selector: 'span' })

    expect(screen.queryByRole('button', { name: 'Liberar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ayuda: Liberar ubicación' })).not.toBeInTheDocument()
  })
})
