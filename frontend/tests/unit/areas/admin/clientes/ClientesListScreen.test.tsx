import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ClientesListScreen } from '../../../../../src/areas/admin/clientes/ClientesListScreen'
import type { RolDePrueba } from '../../../utils/permisosDePrueba'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const CLIENTE_1 = {
  id: '11111111-1111-4111-8111-111111111111',
  codigo: 'C001',
  nombre: 'Kiosco La Esquina',
  razon_social: null,
  documento_tipo: 'DNI',
  documento_numero: '30123456',
  direccion: 'Av. San Martín 1420',
  contacto: 'Rocío',
  telefono: null,
  email: null,
  lista_precio_id: null,
  limite_credito: '5000.00',
  politica_credito: 'BLOQUEAR',
  tolerancia_offline_tipo: null,
  tolerancia_offline_valor: null,
  estado_facturacion_default: null,
  es_consumidor_final: false,
  estado: 'ACTIVO',
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const CONSUMIDOR_FINAL = { ...CLIENTE_1, id: '22222222-2222-4222-8222-222222222222', nombre: 'Consumidor final', es_consumidor_final: true, codigo: null }

const SIN_PERMISO_DE_CLIENTES = 'No tenés permiso para gestionar clientes.'

/** Monta la pantalla con `['yo']` ya sembrado (auxiliar compartido de la
 * tarea 6.7 del change 06b). GES y SUP tienen `GESTIONAR_CLIENTES`
 * (`01-dominio.md` §19); VEN no tiene ninguno de administración. */
function renderPantalla(rol: RolDePrueba = 'GES') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/clientes']}>
        <ClientesListScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Grupo 8, tarea 8.3: para comprobar que la fila navega hace falta una
 * ruta destino real (no alcanza con `<ClientesListScreen />` sola). */
function renderPantallaConRutas(rol: RolDePrueba = 'GES') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/clientes']}>
        <Routes>
          <Route path="/admin/clientes" element={<ClientesListScreen />} />
          <Route path="/admin/clientes/:clienteId" element={<p>Ficha de cliente</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Change 07, grupo 5, tarea 5.2: listado con filtro por texto y por
 * estado, insignia de estado, marca de consumidor final. Visibilidad por
 * `GESTIONAR_CLIENTES` de `['yo']` (`design.md` D3, mismo criterio B2 que
 * `ProveedoresListScreen.test.tsx`). */
describe('ClientesListScreen (change 07, tarea 5.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los clientes de la primera página', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { items: [CLIENTE_1], cursor_siguiente: null }))

    renderPantalla('GES')

    expect(await screen.findByText('Kiosco La Esquina')).toBeInTheDocument()
    expect(screen.getByText('DNI 30123456')).toBeInTheDocument()
    expect(await screen.findByRole('table')).toHaveTextContent('Activo')
  })

  it('marca al cliente consumidor final en el listado', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { items: [CONSUMIDOR_FINAL], cursor_siguiente: null }))

    renderPantalla('GES')

    // El nombre del cliente y la insignia dicen los dos "Consumidor final":
    // dos nodos con el mismo texto.
    const apariciones = await screen.findAllByText('Consumidor final')
    expect(apariciones).toHaveLength(2)
  })

  it('sin el permiso en la consulta de sesión no pide clientes y no muestra la tabla', async () => {
    renderPantalla('VEN')

    expect(await screen.findByText(SIN_PERMISO_DE_CLIENTES)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('si el servidor rechaza aunque la interfaz creía tener el permiso, muestra la falta de permiso sin tabla y sin error genérico (red de seguridad, SEG-06)', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
    )

    renderPantalla('GES')

    expect(await screen.findByText(SIN_PERMISO_DE_CLIENTES)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/no se pudieron obtener los clientes/i)).not.toBeInTheDocument()
  })
})

/** Grupo 8, tarea 8.3 (decisión del usuario 2026-09-29): toda la fila abre
 * la ficha, conservando el nombre como `<Link>` real para el teclado. */
describe('ClientesListScreen: fila clicable (grupo 8, tarea 8.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('hacer clic en una celda sin enlace (documento) abre la ficha del cliente', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { items: [CLIENTE_1], cursor_siguiente: null }))
    const usuarioEvento = userEvent.setup()

    renderPantallaConRutas('GES')

    const celdaDocumento = await screen.findByText('DNI 30123456')
    await usuarioEvento.click(celdaDocumento)

    expect(await screen.findByText('Ficha de cliente')).toBeInTheDocument()
  })

  it('hacer clic en la insignia de estado abre la ficha del cliente', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { items: [CLIENTE_1], cursor_siguiente: null }))
    const usuarioEvento = userEvent.setup()

    renderPantallaConRutas('GES')

    const tabla = await screen.findByRole('table')
    const insigniaEstado = within(tabla).getByText('Activo')
    await usuarioEvento.click(insigniaEstado)

    expect(await screen.findByText('Ficha de cliente')).toBeInTheDocument()
  })
})
