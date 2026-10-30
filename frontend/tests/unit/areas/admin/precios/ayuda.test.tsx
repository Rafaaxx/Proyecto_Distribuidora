/**
 * Change 16b, tarea 5.1: ayuda contextual en las pantallas de listas de precios (spec
 * `ayuda-contextual`, requisito "Las pantallas de listas de precios explican sus reglas"; PRC-02,
 * PRC-12, PRC-13; ADR-051).
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { BorradorScreen } from '../../../../../src/areas/admin/precios/BorradorScreen'
import { ListaDetalleScreen } from '../../../../../src/areas/admin/precios/ListaDetalleScreen'
import { ListaFormScreen } from '../../../../../src/areas/admin/precios/ListaFormScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { LISTA_ID, montarApi, reglasDeBorrador, reglasDeDetalle } from './preciosDePrueba'

function montar(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/precios/nueva" element={<ListaFormScreen />} />
          <Route path="/admin/precios/:listaId" element={<ListaDetalleScreen />} />
          <Route path="/admin/precios/:listaId/borrador" element={<BorradorScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function ayuda(titulo: string) {
  return screen.getByRole('button', { name: `Ayuda: ${titulo}` })
}

beforeEach(() => {
  apiFetchMock.mockReset()
  Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('ayuda en el formulario de la lista', () => {
  it('el "(?)" del redondeo muestra el ejemplo de $8.571,43 con "Ver más" a precio', async () => {
    montarApi(apiFetchMock, [])
    const usuario = userEvent.setup()
    montar('/admin/precios/nueva')

    await screen.findByLabelText(/múltiplo de redondeo/i)
    await usuario.click(ayuda('Redondeo'))

    expect(screen.getByText(/\$8\.571,43 con múltiplo 100/)).toBeVisible()
    expect(screen.getByRole('link', { name: /ver más/i })).toHaveAttribute('href', '/admin/ayuda/precio')
  })
})

describe('ayuda en el detalle de la lista', () => {
  beforeEach(() => {
    montarApi(apiFetchMock, reglasDeDetalle())
  })

  it('el redondeo por categoría tiene su "(?)"', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/precios/${LISTA_ID}`)
    await screen.findByRole('table', { name: /redondeo por categoría/i })

    await usuario.click(ayuda('Redondeo por categoría'))

    expect(screen.getByText(/manda sobre el redondeo de la lista/)).toBeVisible()
  })

  it('el diálogo de regla de margen explica el tipo de margen y la precedencia', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/precios/${LISTA_ID}`)
    await usuario.click(await screen.findByRole('button', { name: /nueva regla/i }))
    const dialogo = within(await screen.findByRole('dialog'))

    await usuario.click(dialogo.getByRole('button', { name: 'Ayuda: Tipo de margen' }))
    expect(screen.getByText(/markup \$7\.800; margen bruto \$8\.571,43/)).toBeVisible()

    await usuario.click(dialogo.getByRole('button', { name: 'Ayuda: Se aplica a' }))
    expect(screen.getByText(/producto, marca, categoría, proveedor/)).toBeVisible()
    expect(screen.queryByText(/markup \$7\.800/)).not.toBeInTheDocument()
  })
})

describe('ayuda en el borrador', () => {
  beforeEach(() => {
    montarApi(apiFetchMock, reglasDeBorrador())
  })

  it('"Regenerar", las señales y "Productos sin precio" tienen su "(?)"', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/precios/${LISTA_ID}/borrador`)
    await screen.findByRole('table', { name: /precios del borrador/i })

    await usuario.click(ayuda('Borrador de precios'))
    expect(screen.getByText(/Cargar un costo nuevo no cambia ningún precio/)).toBeVisible()

    await usuario.click(ayuda('Señales del precio'))
    expect(screen.getByText(/Costos distintos por presentación/)).toBeVisible()

    await usuario.click(ayuda('Productos sin precio'))
    expect(screen.getByText(/Productos activos a los que el borrador no les pudo calcular precio/)).toBeVisible()
  })

  it('los títulos de sección conservan su nombre accesible (el "(?)" va fuera del encabezado)', async () => {
    montar(`/admin/precios/${LISTA_ID}/borrador`)
    await screen.findByRole('table', { name: /precios del borrador/i })

    expect(screen.getByRole('heading', { level: 2, name: 'Productos sin precio' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Precios' })).toBeInTheDocument()
  })

  it('el diálogo de precio manual tiene su "(?)"', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/precios/${LISTA_ID}/borrador`)
    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(screen.getAllByRole('button', { name: /fijar precio/i })[0])

    await usuario.click(ayuda('Precio manual'))

    expect(screen.getByText(/Se mantiene en los próximos borradores/)).toBeVisible()
  })

  it('el diálogo de publicación explica la vigencia', async () => {
    const usuario = userEvent.setup()
    montar(`/admin/precios/${LISTA_ID}/borrador`)
    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(screen.getByRole('button', { name: /^publicar$/i }))

    await usuario.click(ayuda('Vigencia de la publicación'))

    expect(screen.getByText(/nunca puede ser una fecha pasada/)).toBeVisible()
    expect(screen.getByRole('link', { name: /ver más/i })).toHaveAttribute('href', '/admin/ayuda/precio')
  })
})
