import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Ayuda } from '../../../src/components/ui/Ayuda'
import { AyudaIndiceScreen } from '../../../src/ayuda/AyudaIndiceScreen'
import { AyudaTemaScreen } from '../../../src/ayuda/AyudaTemaScreen'
import { AyudaRutaRoutes } from '../../../src/areas/ruta/ayuda/AyudaRutaRoutes'
import { TEMAS } from '../../../src/ayuda/textos'

/**
 * Change 21, tarea 15.1 (spec `sistema/ayuda-contextual`, "El área de ruta tiene su ayuda sin
 * conexión"; `design.md` D21; ADR-051): `/ruta/ayuda` y `/ruta/ayuda/:tema` con la misma página de
 * tema de `/admin`; "Ver más" navega en la misma ventana dentro de `/ruta` y, en `/admin`, solo si
 * la aplicación corre instalada (también en iPhone, que no usa `display-mode`).
 */
function instalada(valor: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((consulta: string) => ({ matches: valor && consulta.includes('standalone'), media: consulta })),
  )
}

function montarAyuda(ruta: string, clave: Parameters<typeof Ayuda>[0]['clave'] = 'descuentos.acumulable') {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Ayuda clave={clave} />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('páginas de ayuda de /ruta (tarea 15.1)', () => {
  it('/ruta/ayuda lista los temas con enlaces dentro de /ruta', () => {
    render(
      <MemoryRouter initialEntries={['/ruta/ayuda']}>
        <Routes>
          <Route path="/ruta/ayuda/*" element={<AyudaRutaRoutes />} />
        </Routes>
      </MemoryRouter>,
    )
    const primero = Object.keys(TEMAS)[0] as keyof typeof TEMAS
    expect(screen.getByRole('link', { name: TEMAS[primero].titulo })).toHaveAttribute('href', `/ruta/ayuda/${primero}`)
    expect(screen.getAllByRole('link')).toHaveLength(Object.keys(TEMAS).length)
  })

  it('/ruta/ayuda/:tema muestra el tema y "Volver a Ayuda" lleva al índice de /ruta', () => {
    render(
      <MemoryRouter initialEntries={['/ruta/ayuda/descuentos']}>
        <Routes>
          <Route path="/ruta/ayuda/*" element={<AyudaRutaRoutes />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: TEMAS.descuentos.titulo })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a Ayuda' })).toHaveAttribute('href', '/ruta/ayuda')
  })

  it('un tema inexistente avisa y vuelve al índice de /ruta', () => {
    render(
      <MemoryRouter initialEntries={['/ruta/ayuda/nada']}>
        <Routes>
          <Route path="/ruta/ayuda/*" element={<AyudaRutaRoutes />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /no encontramos ese tema/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a Ayuda' })).toHaveAttribute('href', '/ruta/ayuda')
  })

  it('en /admin las pantallas de ayuda siguen con sus rutas de siempre', () => {
    render(
      <MemoryRouter initialEntries={['/admin/ayuda']}>
        <AyudaIndiceScreen />
      </MemoryRouter>,
    )
    const primero = Object.keys(TEMAS)[0] as keyof typeof TEMAS
    expect(screen.getByRole('link', { name: TEMAS[primero].titulo })).toHaveAttribute('href', `/admin/ayuda/${primero}`)

    render(
      <MemoryRouter initialEntries={['/admin/ayuda/nada']}>
        <Routes>
          <Route path="/admin/ayuda/:tema" element={<AyudaTemaScreen />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Volver a Ayuda' })).toHaveAttribute('href', '/admin/ayuda')
  })
})

describe('"Ver más" según el área y la instalación (tarea 15.1)', () => {
  it('en /ruta navega en la misma ventana a /ruta/ayuda/<tema>', async () => {
    instalada(false)
    montarAyuda('/ruta/clientes')
    await userEvent.setup().click(screen.getByRole('button', { name: /^Ayuda:/ }))

    const enlace = screen.getByRole('link', { name: 'Ver más' })
    expect(enlace).toHaveAttribute('href', '/ruta/ayuda/descuentos')
    expect(enlace).not.toHaveAttribute('target')
  })

  it('en /admin, instalada (standalone): navega a /admin/ayuda/<tema> en la misma ventana', async () => {
    instalada(true)
    montarAyuda('/admin/descuentos')
    await userEvent.setup().click(screen.getByRole('button', { name: /^Ayuda:/ }))

    const enlace = screen.getByRole('link', { name: 'Ver más' })
    expect(enlace).toHaveAttribute('href', '/admin/ayuda/descuentos')
    expect(enlace).not.toHaveAttribute('target')
  })

  it('en /admin, instalada en iPhone (navigator.standalone): también en la misma ventana', async () => {
    instalada(false)
    vi.stubGlobal('navigator', { ...globalThis.navigator, standalone: true })
    montarAyuda('/admin/descuentos')
    await userEvent.setup().click(screen.getByRole('button', { name: /^Ayuda:/ }))

    expect(screen.getByRole('link', { name: 'Ver más' })).not.toHaveAttribute('target')
  })

  it('en /admin, en el navegador: abre otra pestaña como siempre', async () => {
    instalada(false)
    montarAyuda('/admin/descuentos')
    await userEvent.setup().click(screen.getByRole('button', { name: /^Ayuda:/ }))

    const enlace = screen.getByRole('link', { name: 'Ver más' })
    expect(enlace).toHaveAttribute('href', '/admin/ayuda/descuentos')
    expect(enlace).toHaveAttribute('target', '_blank')
    expect(enlace).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('sin enrutador (pantallas sueltas) sigue siendo un enlace a otra pestaña', async () => {
    instalada(false)
    render(<Ayuda clave="descuentos.acumulable" />)
    await userEvent.setup().click(screen.getByRole('button', { name: /^Ayuda:/ }))

    expect(screen.getByRole('link', { name: 'Ver más' })).toHaveAttribute('target', '_blank')
  })
})
