import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ListasListScreen } from '../../../../../src/areas/admin/precios/ListasListScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { LISTA_ID, OTRA_LISTA_ID, lista, montarApi } from './preciosDePrueba'

function renderListado() {
  return render(
    <QueryClientProvider client={queryClientConYo('GES')}>
      <MemoryRouter>
        <ListasListScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ListasListScreen (tarea 13.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista cada lista con su redondeo, su versión vigente, si tiene borrador y su estado', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/precios/listas',
        responder: () => ({
          status: 200,
          cuerpo: {
            items: [
              lista(),
              lista({
                id: OTRA_LISTA_ID,
                nombre: 'Mayorista',
                redondeo_multiplo: '0.50',
                redondeo_direccion: 'CERCANO',
                version_vigente: null,
                tiene_borrador: false,
                activo: false,
              }),
            ],
          },
        }),
      },
    ])

    renderListado()

    const general = (await screen.findByRole('link', { name: 'General' })).closest('tr') as HTMLElement
    expect(within(general).getByText(/100,00 · hacia arriba/i)).toBeInTheDocument()
    expect(within(general).getByText('Versión 3')).toBeInTheDocument()
    expect(within(general).getByText(/con borrador/i)).toBeInTheDocument()
    expect(within(general).getByText('Activa')).toBeInTheDocument()

    const mayorista = screen.getByRole('link', { name: 'Mayorista' }).closest('tr') as HTMLElement
    expect(within(mayorista).getByText(/0,50 · al más cercano/i)).toBeInTheDocument()
    expect(within(mayorista).getByText(/sin versión vigente/i)).toBeInTheDocument()
    expect(within(mayorista).getByText(/sin borrador/i)).toBeInTheDocument()
    expect(within(mayorista).getByText('Inactiva')).toBeInTheDocument()
  })

  it('el nombre lleva al detalle de la lista', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/precios/listas', responder: () => ({ status: 200, cuerpo: { items: [lista()] } }) },
    ])

    renderListado()

    expect(await screen.findByRole('link', { name: 'General' })).toHaveAttribute('href', `/admin/precios/${LISTA_ID}`)
  })

  it('sin listas, lo dice', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/precios/listas', responder: () => ({ status: 200, cuerpo: { items: [] } }) }])

    renderListado()

    expect(await screen.findByText(/todav[ií]a no hay listas de precios/i)).toBeInTheDocument()
  })

  it('si la consulta falla, muestra un aviso', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/precios/listas', responder: () => ({ status: 500, cuerpo: { title: 'Error', codigo: 'ERROR_INTERNO' } }) },
    ])

    renderListado()

    expect(await screen.findByText(/no se pudieron obtener las listas de precios/i)).toBeInTheDocument()
  })
})
