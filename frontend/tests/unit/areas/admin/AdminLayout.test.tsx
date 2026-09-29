import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AdminInicio } from '../../../../src/areas/admin/AdminInicio'
import { AdminLayout } from '../../../../src/areas/admin/AdminLayout'
import type { RolDePrueba } from '../../utils/permisosDePrueba'
import { queryClientConYo, yoDePrueba } from '../../utils/permisosDePrueba'

/**
 * Menú, encabezado y ruta índice de `/admin` (tareas 7.2 a 7.6, change
 * 06b). El layout se monta con rutas hijas reales de prueba porque el menú
 * vive en el layout y las rutas absolutas (tarea 10.8 del change 05) solo se
 * comprueban navegando dentro de un `Router`.
 *
 * Los permisos llegan por dos caminos y los dos son reales: el `QueryClient`
 * de las pruebas con permiso viene del auxiliar compartido de la tarea 6.7
 * (siembra `['yo']` para un rol de `01` §19), y para los estados pendiente
 * y de error se intercepta `apiFetch` y se deja que `usePermisos()` consulte
 * de verdad. Nunca `any`.
 */
function montarLayout(queryClient: QueryClient, rutaInicial = '/admin/catalogo') {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rutaInicial]}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="inicio" element={<AdminInicio />} />
            <Route path="catalogo" element={<p>Pantalla de catálogo</p>} />
            <Route path="proveedores" element={<p>Pantalla de proveedores</p>} />
            <Route path="clientes" element={<p>Pantalla de clientes</p>} />
            <Route path="dispositivos" element={<p>Pantalla de dispositivos</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** `QueryClient` sin `['yo']` sembrado: sirve para los estados pendiente y de
 * error, donde la consulta sale de verdad. */
function clienteSinYo() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

const ERROR_DEL_SERVIDOR = { title: 'Error del servidor.', codigo: 'ERROR_INTERNO' }

/** Promesa que nunca resuelve: deja la consulta de sesión pendiente. */
function nuncaResuelve() {
  return new Promise(() => {})
}

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

async function montarRol(rol: RolDePrueba, rutaInicial?: string) {
  montarLayout(queryClientConYo(rol), rutaInicial)
  // La caché sembrada deja `usePermisos()` en "listo" en el primer render;
  // se espera el encabezado para no depender de ese detalle.
  await screen.findByRole('navigation', { name: /navegación de administración/i })
}

/**
 * Spec `identidad/permisos-efectivos`, requisito "El menú de `/admin`
 * muestra solo las secciones que el usuario puede usar" (tarea 7.2,
 * **B1**). Los tres casos son los escenarios de la spec con los roles de
 * `01-dominio.md` §19.
 */
describe('AdminLayout: el menú muestra solo las secciones permitidas (tareas 7.2 y 7.3, B1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('Administración ve Catálogo y Proveedores, y no Dispositivos', async () => {
    await montarRol('GES')

    expect(screen.getByRole('link', { name: 'Catálogo' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Proveedores' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Dispositivos' })).not.toBeInTheDocument()
  })

  it('Supervisor comercial ve Clientes y Dispositivos, y no Catálogo ni Proveedores', async () => {
    // Change 07, grupo 5 (tarea 5.5): `GESTIONAR_CLIENTES` habilita la
    // sección de Clientes también para el Supervisor comercial (`01` §19).
    await montarRol('SUP')

    expect(screen.getByRole('link', { name: 'Clientes' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Dispositivos' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Catálogo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Proveedores' })).not.toBeInTheDocument()
  })

  it('Vendedor/Repartidor no ve ninguna sección', async () => {
    await montarRol('VEN')

    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('con los permisos ya sembrados no hace ninguna petición extra a /yo (ADR-027: una consulta por sesión)', async () => {
    await montarRol('ADM')

    expect(screen.getByRole('link', { name: 'Catálogo' })).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('los enlaces del menú son absolutos: desde /admin/dispositivos, "Catálogo" lleva a /admin/catalogo y no a /admin/dispositivos/catalogo (tarea 10.8 del change 05)', async () => {
    const usuarioEvento = userEvent.setup()
    await montarRol('GES', '/admin/dispositivos')

    await usuarioEvento.click(screen.getByRole('link', { name: 'Catálogo' }))

    expect(await screen.findByText('Pantalla de catálogo')).toBeInTheDocument()
  })

  it('si la consulta de sesión falla, no muestra ninguna sección (falla cerrada)', async () => {
    apiFetchMock.mockResolvedValue(respuesta(500, { title: 'Error del servidor.' }))
    montarLayout(clienteSinYo())

    // El layout siempre se monta; lo que no aparece es ninguna sección.
    expect(await screen.findByRole('navigation', { name: /navegación de administración/i })).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })
})

/**
 * Spec `identidad/permisos-efectivos`, escenarios "Mientras la consulta de
 * sesión carga, no se muestran secciones protegidas", "Si la consulta de
 * sesión falla, se informa y se puede reintentar" y "Si la sesión terminó,
 * se ofrece iniciar sesión" (tarea 7.4, **B1**, `design.md` D3-A, ADR-027
 * y ADR-017).
 */
describe('AdminLayout: estado pendiente y estado de error de la consulta de sesión (tarea 7.4, B1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('mientras /yo está pendiente se muestra el encabezado, pero ninguna sección protegida', () => {
    apiFetchMock.mockReturnValue(nuncaResuelve())
    montarLayout(clienteSinYo())

    expect(screen.getByRole('navigation', { name: /navegación de administración/i })).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('si la consulta falla por un error del servidor, avisa que no pudo obtener los permisos y ofrece reintentar', async () => {
    apiFetchMock.mockResolvedValue(respuesta(500, ERROR_DEL_SERVIDOR))
    montarLayout(clienteSinYo())

    expect(await screen.findByText(/no se pudieron obtener tus permisos/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('reintentar vuelve a consultar /yo y, si responde, muestra las secciones permitidas', async () => {
    const usuarioEvento = userEvent.setup()
    apiFetchMock.mockResolvedValueOnce(respuesta(500, ERROR_DEL_SERVIDOR))
    montarLayout(clienteSinYo())

    await screen.findByRole('button', { name: 'Reintentar' })

    apiFetchMock.mockResolvedValueOnce(respuesta(200, yoDePrueba('GES')))
    await usuarioEvento.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(await screen.findByRole('link', { name: 'Catálogo' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Proveedores' })).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(apiFetchMock).toHaveBeenLastCalledWith('/yo')
  })

  it('si la consulta falla con 401 (la renovación del token fue rechazada), el aviso ofrece iniciar sesión y no reintentar', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(401, { title: 'Sesión terminada.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }),
    )
    montarLayout(clienteSinYo())

    const enlace = await screen.findByRole('link', { name: 'Iniciar sesión' })
    expect(enlace).toHaveAttribute('href', '/admin/login')
    // Reintentar no serviría: sin access token la renovación ya fue
    // rechazada una vez, así que un nuevo intento vuelve a fallar (ADR-017).
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Catálogo' })).not.toBeInTheDocument()
  })
})

/**
 * Spec `identidad/permisos-efectivos`, escenario "El encabezado identifica
 * la sesión" (tarea 7.5, **B4**, `design.md` D6-A). Los tres nombres salen
 * de `GET /api/v1/yo`, que devuelve `usuario`, `organizacion` y `rol` con su
 * `nombre` (ADR-027). No incluye botón de cierre de sesión: ningún
 * documento lo pide para este change.
 */
describe('AdminLayout: el encabezado identifica la sesión (tarea 7.5, B4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  const SESION = {
    usuario: { id: 'u-1', nombre: 'Ana Gómez' },
    organizacion: { id: 'o-1', nombre: 'Distribuidora del Sur' },
    rol: { id: 'r-1', nombre: 'Administración' },
  }

  it('muestra "{usuario} · {organización} · {rol}" con los nombres de /yo', async () => {
    montarLayout(queryClientConYo('GES', SESION))

    expect(await screen.findByText('Ana Gómez · Distribuidora del Sur · Administración')).toBeInTheDocument()
  })

  it('mientras /yo está pendiente no inventa ningún nombre de sesión (el separador "·" solo aparece con los tres nombres)', () => {
    apiFetchMock.mockReturnValue(nuncaResuelve())
    montarLayout(clienteSinYo())

    expect(screen.queryByText(/·/)).not.toBeInTheDocument()
  })

  it('si /yo falla, el encabezado tampoco muestra nombres de sesión', async () => {
    apiFetchMock.mockResolvedValue(respuesta(500, ERROR_DEL_SERVIDOR))
    montarLayout(clienteSinYo())

    await screen.findByText(/no se pudieron obtener tus permisos/i)

    expect(screen.queryByText(/·/)).not.toBeInTheDocument()
  })
})

/**
 * Spec `identidad/permisos-efectivos`, escenarios "Administración ve
 * Catálogo y Proveedores, no Dispositivos", "Supervisor comercial ve solo
 * Dispositivos" y "Un usuario sin secciones de administración" (tarea 7.6,
 * **B3**, `design.md` D5-A). `/admin/inicio` es a donde lleva el login y
 * espera `/yo` antes de decidir; usa la misma lista de secciones que el
 * menú, así que no puede desincronizarse de él.
 */
describe('AdminLayout: la ruta índice /admin/inicio (tarea 7.6, B3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('Administración aterriza en Catálogo, la primera sección permitida', async () => {
    montarLayout(queryClientConYo('GES'), '/admin/inicio')

    expect(await screen.findByText('Pantalla de catálogo')).toBeInTheDocument()
  })

  it('Supervisor comercial aterriza en Clientes, la primera sección permitida (change 07, tarea 5.5)', async () => {
    // `Clientes` precede a `Dispositivos` en `SECCIONES`, y el Supervisor
    // comercial tiene `GESTIONAR_CLIENTES` (`01` §19): el aterrizaje sigue
    // el orden del menú (B3), no un orden fijo por rol.
    montarLayout(queryClientConYo('SUP'), '/admin/inicio')

    expect(await screen.findByText('Pantalla de clientes')).toBeInTheDocument()
  })

  it('Vendedor/Repartidor ve que no tiene secciones de administración disponibles', async () => {
    montarLayout(queryClientConYo('VEN'), '/admin/inicio')

    expect(
      await screen.findByText('Tu usuario no tiene secciones de administración disponibles'),
    ).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('mientras /yo está pendiente espera y no redirige a ninguna sección (B1)', () => {
    apiFetchMock.mockReturnValue(nuncaResuelve())
    montarLayout(clienteSinYo(), '/admin/inicio')

    expect(screen.getByText(/cargando/i)).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('si /yo falla no afirma que no hay secciones: informa el aviso del layout (B1)', async () => {
    apiFetchMock.mockResolvedValue(respuesta(500, ERROR_DEL_SERVIDOR))
    montarLayout(clienteSinYo(), '/admin/inicio')

    await screen.findByText(/no se pudieron obtener tus permisos/i)

    expect(screen.queryByText(/tu usuario no tiene secciones/i)).not.toBeInTheDocument()
  })
})
