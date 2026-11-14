import 'fake-indexeddb/auto'

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../../../../src/lib/api/httpClient', async () => {
  const real = await vi.importActual<typeof import('../../../../src/lib/api/httpClient')>(
    '../../../../src/lib/api/httpClient',
  )
  const { yoDePrueba } = await import('../../utils/permisosDePrueba')
  return {
    apiFetch: (ruta: string, init?: RequestInit) => {
      if (ruta === '/yo') {
        return Promise.resolve({ ok: true, status: 200, json: async () => yoDePrueba('ADM') })
      }
      return real.apiFetch(ruta, init)
    },
  }
})

import { AppRoutes } from '../../../../src/app/AppRoutes'

function montar(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

describe('título de la pestaña en /admin', () => {
  it.each([
    ['/admin/inicio', 'Para revisar', 'Inicio · Distribuidora'],
    ['/admin/dispositivos', 'Dispositivos', 'Dispositivos · Distribuidora'],
    ['/admin/catalogo/productos', 'Productos', 'Catálogo · Distribuidora'],
  ])('%s usa el nombre de la sección del menú', async (ruta, encabezado, titulo) => {
    montar(ruta)
    await screen.findByRole('heading', { name: new RegExp(encabezado, 'i') }, { timeout: 15_000 })
    expect(document.title).toBe(titulo)
  }, 20_000)

  it('una dirección inexistente dentro de /admin conserva el título de la 404', async () => {
    montar('/admin/no-existe')
    await screen.findByRole('heading', { name: 'Esta página no existe' })
    expect(document.title).toBe('Esta página no existe · Distribuidora')
  })
})
