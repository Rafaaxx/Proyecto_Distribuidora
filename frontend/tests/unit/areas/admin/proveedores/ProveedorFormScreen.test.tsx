import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ProveedorFormScreen } from '../../../../../src/areas/admin/proveedores/ProveedorFormScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PROVEEDOR = {
  id: '11111111-1111-4111-8111-111111111111',
  nombre: 'Bodega Andina',
  cuit: null,
  contacto: null,
  telefono: null,
  email: null,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const SIN_PERMISO_DE_PROVEEDORES = 'No tenés permiso para gestionar proveedores.'

/** Monta con `['yo']` ya sembrado (auxiliar compartido de la tarea 6.7): el
 * permiso de la pantalla (`GESTIONAR_PROVEEDORES`) y el del enlace "Cargar
 * costos" (`EDITAR_COSTOS`) salen de la consulta de sesión. El default es el
 * rol Administración de `01-dominio.md` §19, que tiene ambos. */
function renderAlta(queryClient: QueryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/proveedores/nuevo']}>
        <Routes>
          <Route path="/admin/proveedores" element={<p>Listado de proveedores</p>} />
          <Route path="/admin/proveedores/nuevo" element={<ProveedorFormScreen />} />
          <Route path="/admin/proveedores/:proveedorId" element={<ProveedorFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderEdicion(proveedorId: string, queryClient: QueryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/proveedores/${proveedorId}`]}>
        <Routes>
          <Route path="/admin/proveedores" element={<p>Listado de proveedores</p>} />
          <Route path="/admin/proveedores/:proveedorId" element={<ProveedorFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Tarea 11.3: alta, nombre duplicado del servidor, y desactivar un
 * proveedor con productos activos (spec `administracion-de-proveedores`).
 */
describe('ProveedorFormScreen: alta (tarea 11.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('da de alta un proveedor con un único envío', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, PROVEEDOR))

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Bodega Andina')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear proveedor/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1))
    const [ruta, opciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe('/proveedores')
    expect(opciones.method).toBe('POST')
    expect(JSON.parse(String(opciones.body))).toMatchObject({ nombre: 'Bodega Andina' })
  })

  it('nombre duplicado informado por el servidor se muestra junto al campo y conserva lo cargado', async () => {
    apiFetchMock.mockImplementation(() =>
      Promise.resolve(respuesta(409, { title: 'El nombre ya está en uso.', codigo: 'NOMBRE_DUPLICADO' })),
    )

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Bodega Andina')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear proveedor/i }))

    expect(await screen.findByText('El nombre ya está en uso.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('Bodega Andina')
  })

  /** Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): tras el alta
   * vuelve al listado de proveedores, no a la ficha del proveedor recién
   * creado -- mismo criterio que clientes. */
  it('después de crear el proveedor vuelve al listado de proveedores', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, PROVEEDOR))

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Bodega Andina')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear proveedor/i }))

    expect(await screen.findByText('Listado de proveedores')).toBeInTheDocument()
  })
})

describe('ProveedorFormScreen: ficha de edición (tarea 11.3, D5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('desactivar un proveedor con productos activos muestra el error y el proveedor sigue activo', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(
          respuesta(409, {
            title: 'El proveedor tiene productos activos.',
            codigo: 'PROVEEDOR_CON_PRODUCTOS_ACTIVOS',
          }),
        )
      }
      return Promise.resolve(respuesta(200, PROVEEDOR))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(PROVEEDOR.id)

    const botonDesactivar = await screen.findByRole('button', { name: /desactivar/i })
    await usuarioEvento.click(botonDesactivar)

    expect(await screen.findByText('El proveedor tiene productos activos.')).toBeInTheDocument()
    // El botón sigue ofreciendo "Desactivar": el proveedor sigue activo.
    expect(screen.getByRole('button', { name: /desactivar/i })).toBeInTheDocument()
  })

  it('desactivar un proveedor sin productos activos lo deja inactivo (ofrece "Reactivar")', async () => {
    let activo = true
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        activo = false
        return Promise.resolve(respuesta(200, { ...PROVEEDOR, activo }))
      }
      return Promise.resolve(respuesta(200, { ...PROVEEDOR, activo }))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(PROVEEDOR.id)

    const botonDesactivar = await screen.findByRole('button', { name: /desactivar/i })
    await usuarioEvento.click(botonDesactivar)

    expect(await screen.findByRole('button', { name: /reactivar/i })).toBeInTheDocument()
  })

  /**
   * Tarea 8.4 del change 06b, escenario "Enlace 'Cargar costos' desde la
   * ficha del proveedor según el permiso" de la spec
   * `administracion-de-proveedores`: el enlace se decide con `EDITAR_COSTOS`
   * de la consulta de sesión `['yo']` (ADR-027), no preguntando al servidor.
   * Un usuario con `GESTIONAR_PROVEEDORES` pero sin `EDITAR_COSTOS` no lo ve.
   *
   * Línea base de la suite: 4 casos, todos verdes antes de la tarea 8.4.
   */
  it('con GESTIONAR_PROVEEDORES y EDITAR_COSTOS muestra el enlace "Cargar costos" con el href correcto', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, PROVEEDOR))

    renderEdicion(PROVEEDOR.id)

    const enlace = await screen.findByRole('link', { name: /cargar costos/i })
    expect(enlace).toHaveAttribute('href', `/admin/proveedores/${PROVEEDOR.id}/costos`)
  })

  it('con GESTIONAR_PROVEEDORES pero sin EDITAR_COSTOS no muestra el enlace "Cargar costos"', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, PROVEEDOR))
    const queryClient = queryClientConYo('GES', { permisos: ['GESTIONAR_PROVEEDORES'] })

    renderEdicion(PROVEEDOR.id, queryClient)

    // La ficha se abre igual (el permiso de la pantalla sí está): lo que
    // falta es solo el del enlace.
    await screen.findByRole('button', { name: /desactivar/i })
    expect(screen.queryByRole('link', { name: /cargar costos/i })).not.toBeInTheDocument()
  })

  it('sin GESTIONAR_PROVEEDORES no pide la ficha del proveedor y muestra que falta el permiso (B2)', async () => {
    renderEdicion(PROVEEDOR.id, queryClientConYo('VEN'))

    expect(await screen.findByText(SIN_PERMISO_DE_PROVEEDORES)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  /** Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): guardar la
   * edición de la ficha del proveedor vuelve al listado, mismo criterio que
   * clientes. */
  it('después de guardar la edición vuelve al listado de proveedores', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...PROVEEDOR, nombre: 'Bodega Andina S.A.' }))
      }
      return Promise.resolve(respuesta(200, PROVEEDOR))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(PROVEEDOR.id)

    const campoNombre = await screen.findByLabelText(/^nombre$/i)
    await usuarioEvento.clear(campoNombre)
    await usuarioEvento.type(campoNombre, 'Bodega Andina S.A.')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(await screen.findByText('Listado de proveedores')).toBeInTheDocument()
  })
})
