import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../../src/app/AppRoutes'

describe('ruteo de áreas (docs/02 §13.1: /ruta y /admin cargadas de forma diferida)', () => {
  it('muestra la pantalla de /ruta al navegar a /ruta', async () => {
    render(
      <MemoryRouter initialEntries={['/ruta']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/área de ruta/i)).toBeInTheDocument()
  })

  it('muestra la pantalla de /admin al navegar a /admin', async () => {
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/área de administración/i)).toBeInTheDocument()
  })

  it('redirige la raíz a /ruta', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/área de ruta/i)).toBeInTheDocument()
  })
})
