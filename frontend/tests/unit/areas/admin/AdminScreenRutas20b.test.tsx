/**
 * Change 20b, tareas 10.1 y 10.4: las rutas `/admin/usuarios` y `/admin/mi-contrasena` existen en
 * `AdminScreen` y respetan el permiso (ADR-027, SEG-06).
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { enrutar } from '../../utils/enrutarApi'
import { yoDePrueba, type RolDePrueba } from '../../utils/permisosDePrueba'

function servidor(rol: RolDePrueba) {
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/yo', responder: () => ({ status: 200, cuerpo: yoDePrueba(rol) }) },
    { metodo: 'GET', ruta: '/identidad/usuarios', responder: () => ({ status: 200, cuerpo: [] }) },
    { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: [] }) },
  ])
}

/** `AdminScreen` guarda su `QueryClient` en el módulo: cada prueba lo reimporta para partir de una sesión limpia. */
async function montar(ruta: string) {
  vi.resetModules()
  const { AdminScreen } = await import('../../../../src/areas/admin/AdminScreen')
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AdminScreen />
    </MemoryRouter>,
  )
}

describe('rutas del change 20b en AdminScreen', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('/usuarios abre el listado de usuarios para quien tiene ADMIN_USUARIOS', async () => {
    servidor('ADM')
    await montar('/usuarios')

    expect(await screen.findByRole('heading', { name: 'Usuarios' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Nuevo usuario' })).toBeInTheDocument()
  })

  it('/usuarios sin ADMIN_USUARIOS muestra que no tiene permiso', async () => {
    servidor('SUP')
    await montar('/usuarios')

    expect(await screen.findByText(/no tenés permiso para administrar usuarios/i)).toBeInTheDocument()
  })

  it('/mi-contrasena abre la pantalla para cualquier usuario con sesión', async () => {
    servidor('VEN')
    await montar('/mi-contrasena')

    expect(await screen.findByRole('heading', { name: 'Mi contraseña' })).toBeInTheDocument()
    expect(screen.getByLabelText('Tu contraseña actual')).toBeInTheDocument()
  })
})
