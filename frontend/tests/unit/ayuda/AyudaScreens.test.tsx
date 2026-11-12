import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AyudaIndiceScreen } from '../../../src/ayuda/AyudaIndiceScreen'
import { AyudaTemaScreen } from '../../../src/ayuda/AyudaTemaScreen'

/**
 * Páginas "Ver más" (spec `ayuda-contextual`, requisito "Las páginas 'Ver más' explican los
 * temas largos"; ADR-051, D5 y D7 = A). No piden datos: se comprueba que `fetch` no se llama.
 */
function montar(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/admin/ayuda" element={<AyudaIndiceScreen />} />
        <Route path="/admin/ayuda/:tema" element={<AyudaTemaScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Índice de ayuda', () => {
  it('lista los tres temas con enlaces a su página', () => {
    montar('/admin/ayuda')

    expect(screen.getByRole('link', { name: 'Cómo se aplican los descuentos' })).toHaveAttribute(
      'href',
      '/admin/ayuda/descuentos',
    )
    expect(screen.getByRole('link', { name: 'Cómo funcionan los topes' })).toHaveAttribute('href', '/admin/ayuda/topes')
    expect(screen.getByRole('link', { name: 'Cómo se calcula el precio de una lista' })).toHaveAttribute(
      'href',
      '/admin/ayuda/precio',
    )
  })
})

describe('Página de un tema', () => {
  it('descuentos: título, secciones y el ejemplo de 9,84 %', () => {
    montar('/admin/ayuda/descuentos')

    expect(screen.getByRole('heading', { level: 1, name: 'Cómo se aplican los descuentos' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: '2. Entre las no acumulables gana una sola' })).toBeInTheDocument()
    expect(screen.getByText(/8 % y después 2 % = 9,84 %, no 10 %/)).toBeInTheDocument()
  })

  it('topes: una autorización cubre toda la venta', () => {
    montar('/admin/ayuda/topes')

    expect(screen.getByRole('heading', { level: 1, name: 'Cómo funcionan los topes' })).toBeInTheDocument()
    expect(screen.getByText(/una sola alcanza para toda la venta/)).toBeInTheDocument()
  })

  it('precio: el ejemplo del vino de $6.000 con $7.800, $8.571,43 y $8.600', () => {
    montar('/admin/ayuda/precio')

    expect(screen.getByRole('heading', { level: 1, name: 'Cómo se calcula el precio de una lista' })).toBeInTheDocument()
    expect(screen.getByText(/vino con costo \$6\.000 y margen bruto 30 % → \$8\.571,43/)).toBeInTheDocument()
  })

  it('cada página ofrece volver al índice', () => {
    montar('/admin/ayuda/topes')

    expect(screen.getByRole('link', { name: /volver a ayuda/i })).toHaveAttribute('href', '/admin/ayuda')
  })

  it('un tema inexistente muestra el aviso y un enlace al índice', () => {
    montar('/admin/ayuda/no-existe')

    expect(screen.getByText('No encontramos ese tema de ayuda')).toBeInTheDocument()
    const enlace = screen.getByRole('link', { name: /ayuda/i })
    expect(enlace).toHaveAttribute('href', '/admin/ayuda')
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument()
  })

  it('ninguna página hace una petición', () => {
    const peticion = vi.fn()
    vi.stubGlobal('fetch', peticion)

    for (const ruta of ['/admin/ayuda', '/admin/ayuda/descuentos', '/admin/ayuda/topes', '/admin/ayuda/precio', '/admin/ayuda/x']) {
      const { unmount } = montar(ruta)
      unmount()
    }

    expect(peticion).not.toHaveBeenCalled()
  })
})
