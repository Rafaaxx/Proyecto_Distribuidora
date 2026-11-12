/**
 * Change 26, tarea 10.1 (D11; ADR-027, SEG-06): la ruta `/admin/reportes` existe en `AdminScreen`, abre «Ventas»
 * para quien tiene `VER_REPORTES` y no muestra datos a quien no lo tiene.
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { enrutar } from '../../../utils/enrutarApi'
import { yoDePrueba, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { reporteDeVentas } from './reporteDePrueba'

function servidor(rol: RolDePrueba) {
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/yo', responder: () => ({ status: 200, cuerpo: yoDePrueba(rol) }) },
    { metodo: 'GET', ruta: '/reportes/ventas', responder: () => ({ status: 200, cuerpo: reporteDeVentas(rol === 'CON') }) },
  ])
}

/** `AdminScreen` guarda su `QueryClient` en el módulo: cada prueba lo reimporta para partir de una sesión limpia. */
async function montar(ruta: string) {
  vi.resetModules()
  const { AdminScreen } = await import('../../../../../src/areas/admin/AdminScreen')
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AdminScreen />
    </MemoryRouter>,
  )
}

describe('ruta /reportes en AdminScreen (change 26)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('/reportes abre «Ventas» para Consulta/Dirección', async () => {
    servidor('CON')
    await montar('/reportes')

    expect(await screen.findByRole('heading', { name: 'Reportes' })).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Por día' })).toBeInTheDocument()
  })

  it('/reportes sin VER_REPORTES no muestra datos ni pide el reporte', async () => {
    servidor('VEN')
    await montar('/reportes')

    expect(await screen.findByRole('heading', { name: 'Reportes' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(apiFetchMock.mock.calls.some(([ruta]) => String(ruta).startsWith('/reportes'))).toBe(false)
  })
})
