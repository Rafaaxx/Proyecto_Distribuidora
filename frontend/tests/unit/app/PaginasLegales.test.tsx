import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../../../src/app/AppRoutes'

describe('páginas legales públicas', () => {
  it.each([
    ['/privacidad', 'Política de privacidad'],
    ['/terminos', 'Términos y condiciones'],
  ])('%s muestra «%s», «Próximamente» y un botón para volver al inicio', async (ruta, titulo) => {
    render(
      <MemoryRouter initialEntries={[ruta]}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { level: 1, name: titulo })).toBeInTheDocument()
    expect(screen.getByText('Próximamente')).toBeInTheDocument()
    expect(screen.getByText('Estamos preparando este documento.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /volver al inicio/i })).toHaveAttribute('href', '/')
    expect(document.title).toBe(`${titulo} · Distribuidora`)
  })
})
