import 'fake-indexeddb/auto'

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../../../src/lib/api/httpClient', async () => {
  const real = await vi.importActual<typeof import('../../../src/lib/api/httpClient')>('../../../src/lib/api/httpClient')
  const { yoDePrueba } = await import('../utils/permisosDePrueba')
  return {
    apiFetch: (ruta: string, init?: RequestInit) => {
      if (ruta === '/yo') {
        return Promise.resolve({ ok: true, status: 200, json: async () => yoDePrueba('ADM') })
      }
      return real.apiFetch(ruta, init)
    },
  }
})

import { AppRoutes } from '../../../src/app/AppRoutes'
import { PaginaNoEncontrada } from '../../../src/app/PaginaNoEncontrada'

describe('PaginaNoEncontrada', () => {
  it('muestra el mensaje y un botón que vuelve al destino recibido', () => {
    render(
      <MemoryRouter>
        <PaginaNoEncontrada destino="/admin/inicio" textoDelBoton="Volver al inicio" />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Esta página no existe' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver al inicio' })).toHaveAttribute('href', '/admin/inicio')
  })

  it('pone el título de la pestaña y lo restaura al salir', () => {
    document.title = 'Distribuidora'
    const { unmount } = render(
      <MemoryRouter>
        <PaginaNoEncontrada destino="/" textoDelBoton="Volver" />
      </MemoryRouter>,
    )
    expect(document.title).toBe('Esta página no existe · Distribuidora')
    unmount()
    expect(document.title).toBe('Distribuidora')
  })
})

describe('rutas inexistentes en los tres niveles', () => {
  it('una dirección suelta muestra la 404 y vuelve a /', async () => {
    render(
      <MemoryRouter initialEntries={['/no-existe']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Esta página no existe' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /volver al inicio/i })).toHaveAttribute('href', '/')
  })

  it('dentro de /admin la muestra con el menú y vuelve a /admin/inicio', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/no-existe']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    // Primer import diferido del área de administración: tarda más en frío.
    expect(
      await screen.findByRole('heading', { name: 'Esta página no existe' }, { timeout: 15_000 }),
    ).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Navegación de administración' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /volver al inicio/i })).toHaveAttribute('href', '/admin/inicio')
  }, 20_000)
})
