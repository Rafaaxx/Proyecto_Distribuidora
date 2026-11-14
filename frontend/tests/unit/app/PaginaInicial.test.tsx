import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppRoutes } from '../../../src/app/AppRoutes'
import { PaginaInicial } from '../../../src/app/PaginaInicial'

function renderPagina() {
  return render(
    <MemoryRouter>
      <PaginaInicial />
    </MemoryRouter>,
  )
}

describe('página de presentación en /', () => {
  it('se muestra en la ruta / con un único h1 y los accesos', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getAllByRole('link', { name: /administración/i }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByRole('link', { name: /vendedor/i }).length).toBeGreaterThanOrEqual(1)
  })

  it('lleva a /admin y a /ruta desde todos los accesos, en la portada y en el cierre', () => {
    renderPagina()

    const admin = screen.getAllByRole('link', { name: /administración/i })
    const ruta = screen.getAllByRole('link', { name: /vendedor/i })
    expect(admin.length).toBeGreaterThanOrEqual(2)
    expect(ruta.length).toBeGreaterThanOrEqual(2)
    for (const enlace of admin) expect(enlace).toHaveAttribute('href', '/admin')
    for (const enlace of ruta) expect(enlace).toHaveAttribute('href', '/ruta')
  })

  it('presenta las secciones principales con su título', () => {
    renderPagina()

    for (const titulo of [
      /qué resuelve/i,
      /en la calle/i,
      /en la oficina/i,
      /cómo funciona/i,
      /seguridad y confianza/i,
    ]) {
      expect(screen.getByRole('heading', { name: titulo })).toBeInTheDocument()
    }
  })

  it('cuenta lo que el sistema hace: venta sin señal, nota de venta y copias de seguridad', () => {
    renderPagina()

    expect(screen.getAllByText(/sin señal/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/nota de venta/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/copias de seguridad/i).length).toBeGreaterThan(0)
  })

  it('no promete lo que todavía no existe ni ofrece crear una organización', () => {
    renderPagina()

    expect(screen.queryByText(/organizaci/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/afip|arca|factura electr|gps|código de barras/i)).not.toBeInTheDocument()
  })

  it('enlaza las páginas legales desde el pie', () => {
    renderPagina()

    const pie = screen.getByRole('contentinfo')
    expect(within(pie).getByRole('link', { name: 'Política de privacidad' })).toHaveAttribute('href', '/privacidad')
    expect(within(pie).getByRole('link', { name: 'Términos y condiciones' })).toHaveAttribute('href', '/terminos')
  })

  it('muestra el contacto con el teléfono como enlace que abre el marcador', () => {
    renderPagina()

    const contacto = screen.getByRole('region', { name: /contacto/i })
    const telefono = within(contacto).getByRole('link', { name: /\+54 9 261 650-7807/ })
    expect(telefono).toHaveAttribute('href', 'tel:+5492616507807')
  })

  it('pone el título de la pestaña', () => {
    renderPagina()
    expect(document.title).toBe('Inicio · Distribuidora')
  })
})
