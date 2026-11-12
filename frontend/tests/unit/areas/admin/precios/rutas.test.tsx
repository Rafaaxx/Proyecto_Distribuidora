import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import PreciosArea from '../../../../../src/areas/admin/precios/PreciosArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import {
  LISTA_ID,
  VERSION_HISTORICA,
  VERSION_VIGENTE_ID,
  borrador,
  lista,
  montarApi,
  reglasDeDetalle,
  version,
} from './preciosDePrueba'

function renderEn(ruta: string, rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/precios/*" element={<PreciosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function llamadasAPrecios(): unknown[] {
  return apiFetchMock.mock.calls.filter(([ruta]) => String(ruta).startsWith('/precios'))
}

describe('rutas de listas de precios en /admin (change 13, tarea 13.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/precios/listas', responder: () => ({ status: 200, cuerpo: { items: [lista()] } }) },
      { metodo: 'GET', ruta: `/precios/listas/${LISTA_ID}/borrador`, responder: () => ({ status: 200, cuerpo: borrador() }) },
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/versiones/${VERSION_VIGENTE_ID}/precios`,
        responder: () => ({ status: 200, cuerpo: { version: version(), precios: [], siguiente_cursor: null } }),
      },
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/versiones/${VERSION_HISTORICA.id}/precios`,
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
      ...reglasDeDetalle(),
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['/admin/precios', /nueva lista/i],
    ['/admin/precios/nueva', /crear lista/i],
    [`/admin/precios/${LISTA_ID}`, /reglas de margen/i],
    [`/admin/precios/${LISTA_ID}/editar`, /guardar cambios/i],
    [`/admin/precios/${LISTA_ID}/borrador`, /regenerar/i],
    [`/admin/precios/${LISTA_ID}/versiones/${VERSION_VIGENTE_ID}`, /versi[oó]n 3/i],
  ])('%s se resuelve a su pantalla', async (ruta, texto) => {
    renderEn(ruta)

    expect((await screen.findAllByText(texto)).length).toBeGreaterThan(0)
  })

  it('con solo PUBLICAR_LISTAS ve el listado sin "Nueva lista"', async () => {
    renderEn('/admin/precios', 'GES', ['PUBLICAR_LISTAS'])

    expect(await screen.findByRole('link', { name: 'General' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /nueva lista/i })).not.toBeInTheDocument()
  })

  it('con GESTIONAR_LISTAS el listado ofrece "Nueva lista"', async () => {
    renderEn('/admin/precios', 'GES', ['GESTIONAR_LISTAS'])

    expect(await screen.findByRole('link', { name: /nueva lista/i })).toHaveAttribute('href', '/admin/precios/nueva')
  })

  it('un Vendedor sin permisos de listas: el listado muestra la falta de permiso y no pide ningún dato de listas', async () => {
    renderEn('/admin/precios', 'VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las listas de precios/i)).toBeInTheDocument()
    expect(llamadasAPrecios()).toHaveLength(0)
  })

  it.each([
    [`/admin/precios/${LISTA_ID}`],
    [`/admin/precios/${LISTA_ID}/borrador`],
    [`/admin/precios/${LISTA_ID}/versiones/${VERSION_VIGENTE_ID}`],
  ])('sin permisos de listas, %s muestra la falta de permiso y no pide nada', async (ruta) => {
    renderEn(ruta, 'VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las listas de precios/i)).toBeInTheDocument()
    expect(llamadasAPrecios()).toHaveLength(0)
  })

  it.each([['/admin/precios/nueva'], [`/admin/precios/${LISTA_ID}/editar`]])(
    'con solo PUBLICAR_LISTAS, %s muestra la falta de permiso para gestionar listas',
    async (ruta) => {
      renderEn(ruta, 'GES', ['PUBLICAR_LISTAS'])

      expect(await screen.findByText(/no ten[eé]s permiso para gestionar listas de precios/i)).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /crear lista|guardar cambios/i })).not.toBeInTheDocument()
    },
  )
})

describe('entrada de menú "Listas de precios" por rol (spec administracion-de-listas)', () => {
  const ve = (rol: RolDePrueba) =>
    seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Listas de precios')

  it('está declarada y la ven Administrador y Administración, no Supervisor, Vendedor ni Consulta', () => {
    expect(SECCIONES.some((s) => s.ruta === '/admin/precios')).toBe(true)
    expect((['ADM', 'GES', 'SUP', 'VEN', 'CON'] as const).map(ve)).toEqual([true, true, false, false, false])
  })

  it('un usuario con solo GESTIONAR_LISTAS la ve, y uno con solo PUBLICAR_LISTAS también', () => {
    const seccionesCon = (permiso: string) => seccionesPermitidas((p) => p === permiso).map((s) => s.etiqueta)

    expect(seccionesCon('GESTIONAR_LISTAS')).toContain('Listas de precios')
    expect(seccionesCon('PUBLICAR_LISTAS')).toContain('Listas de precios')
    expect(seccionesCon('GESTIONAR_CLIENTES')).not.toContain('Listas de precios')
  })
})
