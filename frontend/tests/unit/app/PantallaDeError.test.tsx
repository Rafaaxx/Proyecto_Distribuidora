import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { lazy, Suspense } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PantallaDeError } from '../../../src/app/PantallaDeError'

function montarConError(error: Error) {
  function Rota(): never {
    throw error
  }
  const router = createMemoryRouter([{ path: '*', element: <Rota />, errorElement: <PantallaDeError /> }])
  return render(<RouterProvider router={router} />)
}

/**
 * Change 27a, D19: en lugar de la pantalla por defecto de React Router («Unexpected Application
 * Error!»), un fallo de carga de módulo tras una actualización invita a recargar; cualquier otro
 * error muestra un mensaje genérico en español.
 */
describe('PantallaDeError', () => {
  const recargar = vi.fn()
  const original = window.location

  afterEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(window, 'location', { value: original, configurable: true })
    recargar.mockReset()
  })

  function falsearRecarga() {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    Object.defineProperty(window, 'location', {
      value: { ...original, reload: recargar },
      configurable: true,
    })
  }

  it('ante un error de carga de módulo avisa que hay una versión nueva y recarga', async () => {
    falsearRecarga()
    montarConError(new TypeError('Failed to fetch dynamically imported module: https://x/a.js'))

    expect(screen.getByText('Hay una versión nueva del sistema')).toBeInTheDocument()
    expect(screen.queryByText(/Unexpected Application Error/i)).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Recargar' }))
    expect(recargar).toHaveBeenCalledTimes(1)
  })

  it('ante otro error muestra un mensaje genérico con botón para recargar', async () => {
    falsearRecarga()
    montarConError(new Error('Cannot read properties of undefined'))

    expect(screen.getByText('Algo salió mal')).toBeInTheDocument()
    expect(screen.queryByText('Hay una versión nueva del sistema')).toBeNull()
    expect(screen.queryByText(/Cannot read properties/)).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Recargar' }))
    expect(recargar).toHaveBeenCalledTimes(1)
  })

  it('atrapa el rechazo de una pantalla diferida (React.lazy) dentro de la ruta', async () => {
    falsearRecarga()
    const Diferida = lazy(() => Promise.reject(new TypeError('Importing a module script failed.')))
    const router = createMemoryRouter([
      {
        path: '*',
        element: (
          <Suspense fallback={null}>
            <Diferida />
          </Suspense>
        ),
        errorElement: <PantallaDeError />,
      },
    ])
    render(<RouterProvider router={router} />)

    expect(await screen.findByText('Hay una versión nueva del sistema')).toBeInTheDocument()
  })
})
