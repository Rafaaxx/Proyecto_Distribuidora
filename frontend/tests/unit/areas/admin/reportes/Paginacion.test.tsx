import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Paginacion } from '../../../../../src/areas/admin/reportes/Paginacion'

/**
 * Change 26, tarea 21.7 (spec `reportes/area-de-reportes`, «La navegación entre páginas en `/admin`», escenarios
 * «Recorrer las páginas» y «Una sola página»; D14): «Anterior», «Página {n} de {m}» y «Siguiente».
 */
describe('Paginacion', () => {
  it('en la página 2 de 3 muestra el número y deja ir a las dos', async () => {
    const alCambiar = vi.fn()
    render(<Paginacion pagina={2} paginas={3} alCambiar={alCambiar} etiqueta="Por día" />)

    expect(screen.getByText('Página 2 de 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeEnabled()

    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await userEvent.click(screen.getByRole('button', { name: 'Anterior' }))
    expect(alCambiar.mock.calls).toEqual([[3], [1]])
  })

  it('en la primera deshabilita Anterior y en la última, Siguiente', async () => {
    const alCambiar = vi.fn()
    const { rerender } = render(<Paginacion pagina={1} paginas={3} alCambiar={alCambiar} etiqueta="Por día" />)
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeEnabled()

    rerender(<Paginacion pagina={3} paginas={3} alCambiar={alCambiar} etiqueta="Por día" />)
    expect(screen.getByText('Página 3 de 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    expect(alCambiar).not.toHaveBeenCalled()
  })

  it('con una sola página o sin filas no muestra nada', () => {
    const { container, rerender } = render(<Paginacion pagina={1} paginas={1} alCambiar={vi.fn()} etiqueta="Por día" />)
    expect(container).toBeEmptyDOMElement()

    rerender(<Paginacion pagina={1} paginas={0} alCambiar={vi.fn()} etiqueta="Por día" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('se identifica por la lista a la que pertenece', () => {
    render(<Paginacion pagina={1} paginas={2} alCambiar={vi.fn()} etiqueta="Saldos de clientes" />)

    expect(screen.getByRole('navigation', { name: 'Paginación de Saldos de clientes' })).toBeInTheDocument()
  })
})
