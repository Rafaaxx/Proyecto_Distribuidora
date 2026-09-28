import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RolDePrueba } from '../../utils/permisosDePrueba'
import { yoDePrueba } from '../../utils/permisosDePrueba'

/**
 * El `dispositivo_id` que `httpClient` manda en `/auth/refresh` sale de
 * IndexedDB (`lib/dispositivo/dispositivoId`), que jsdom no tiene. No es
 * lo que se está probando acá, así que se reemplaza por un valor fijo (el
 * mismo criterio que `tests/unit/lib/api/httpClient.test.ts`).
 */
vi.mock('../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))

/**
 * Corte determinístico de la sesión terminada (tareas 11.1 y 11.2 del
 * change 06b, cierre del hallazgo de la 10.5).
 *
 * **Qué faltaba y qué prueba esto.** La verificación manual del paso 13
 * (usuario `INACTIVO`, ADR-028 D9) encontró que el aviso "Iniciar sesión"
 * del layout (spec `identidad/permisos-efectivos`, **B1**, escenario "Si
 * la sesión terminó, se ofrece iniciar sesión") no aparecía: el backend
 * responde 401 por petición y rechaza la renovación (correcto), pero la
 * pantalla de datos que recibió el 401 mostraba su propio error y, al
 * recargar con la sesión muerta, `/admin` quedaba en blanco.
 *
 * La causa no era el mensaje de la pantalla sino el estado de la consulta
 * `['yo']`: `tokenStore` avisaba con `null`, `AdminScreen` respondía
 * `removeQueries(['yo'])`, y en TanStack Query v5 eso **destruye** la
 * consulta y la saca de la caché. El observer de `usePermisos()` sigue
 * apuntando a esa consulta destruida: si tenía datos, el menú sigue
 * mostrando las secciones viejas y nunca aparece el aviso; si estaba en
 * vuelo, el observer queda esperando un resultado que ya fue descartado y
 * la pantalla queda en blanco para siempre. Encima, `usePermisos()` no
 * declaraba `retry`, así que un 401 recién motherboardaba en estado de
 * error después del backoff por defecto (1 s + 2 s + 4 s).
 *
 * Estos casos montan el árbol real (`AdminScreen` con su `QueryClient` de
 * módulo, la suscripción a `tokenStore`, `httpClient` con la renovación de
 * verdad y `AdminLayout`) y simulan el servidor con `fetch`, porque el
 * corte vive justo en la interacción entre las tres piezas. Mockear
 * `apiFetch` -- como hacen los demás archivos de `/admin` -- lo dejaría
 * fuera.
 *
 * `vi.resetModules()` por prueba es obligatorio: el `QueryClient` de
 * `AdminScreen.tsx` es un singleton de módulo y `usePermisos()` usa
 * `staleTime: Infinity` (ADR-027), así que sin reiniciar el registro de
 * módulos el `['yo']` del caso anterior seguiría cacheado.
 */
describe('AdminScreen: la renovación rechazada pasa a "sesión terminada" (tareas 11.1 y 11.2, B1)', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('un 401 en una consulta de datos (no /yo) con la renovación rechazada muestra "Iniciar sesión" y deja el menú sin secciones', async () => {
    const servidor = crearServidorDePrueba()
    servirCon(servidor)
    const { fijarAccessToken } = await import('../../../../src/lib/auth/tokenStore')
    act(() => fijarAccessToken('access-token-vigente'))

    await montarAdmin(`/admin/catalogo/productos/${PRODUCTO_ID}`)

    // Sesión viva: Administración ve Catálogo y Proveedores (01-dominio.md §19)
    // y la ficha del producto se está mostrando.
    expect(await screen.findByRole('heading', { name: /GAS-001/ })).toBeInTheDocument()
    const menu = menuDeAdministracion()
    expect(within(menu).getByRole('link', { name: 'Catálogo' })).toBeInTheDocument()
    expect(within(menu).getByRole('link', { name: 'Proveedores' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Iniciar sesión' })).not.toBeInTheDocument()

    // El usuario pasa a `INACTIVO` por `psql` (ADR-028 D9): a partir de
    // ahora toda petición autenticada responde 401 y la renovación se rechaza.
    servidor.darDeBajaAlUsuario()

    // La siguiente acción es una consulta de datos de otra pantalla: el
    // listado de catálogo. No es `/yo`, que es lo que dispara el corte.
    await userEvent.setup().click(within(menu).getByRole('link', { name: 'Catálogo' }))

    const enlace = await screen.findByRole('link', { name: 'Iniciar sesión' })
    expect(enlace).toHaveAttribute('href', '/admin/login')
    // Reintentar no serviría: sin token la renovación ya fue rechazada una
    // vez, así que un nuevo intento vuelve a fallar (ADR-017).
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    // Falla cerrada: ninguna sección protegida sobrevive a la sesión muerta.
    expect(within(menuDeAdministracion()).queryAllByRole('link')).toHaveLength(0)
    // Y es determinista: una sola renovación en toda la vida de la pantalla
    // y ni un reintento de la consulta de sesión.
    expect(servidor.rutasPedidas('/auth/refresh')).toHaveLength(1)
    expect(servidor.rutasPedidas('/yo')).toHaveLength(1)
  })

  it('el corte no depende de la pantalla ni de que la petición sea de lectura: una escritura rechazada muestra el mismo aviso', async () => {
    // Triangular el comportamiento anterior con otro disparador y otra
    // pantalla: un Supervisor comercial en Dispositivos que intenta
    // revocar. Es un `DELETE` (escritura, lleva `Operation-Id`) y no un
    // `GET`, y el permiso de la pantalla (`GESTIONAR_DISPOSITIVOS`) no
    // tiene nada que ver con el de la otra pantalla.
    const servidor = crearServidorDePrueba({ rol: 'SUP' })
    servirCon(servidor)
    const { fijarAccessToken } = await import('../../../../src/lib/auth/tokenStore')
    act(() => fijarAccessToken('access-token-vigente'))

    await montarAdmin('/admin/dispositivos')

    expect(await screen.findByRole('button', { name: 'Revocar' })).toBeInTheDocument()
    const menu = menuDeAdministracion()
    expect(within(menu).getByRole('link', { name: 'Dispositivos' })).toBeInTheDocument()

    servidor.darDeBajaAlUsuario()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Revocar' }))

    expect(await screen.findByRole('link', { name: 'Iniciar sesión' })).toHaveAttribute('href', '/admin/login')
    expect(within(menuDeAdministracion()).queryAllByRole('link')).toHaveLength(0)
    expect(servidor.rutasPedidas('/auth/refresh')).toHaveLength(1)
  })

  it('al montar /admin sin access token con la renovación rechazada aparece el aviso (no queda en blanco y no reintenta)', async () => {
    // Sesión muerta desde el arranque, que es lo que hay después de recargar
    // la página con la sesión revocada: no hay access token en memoria y el
    // refresh se rechaza.
    const servidor = crearServidorDePrueba({ sesionHabilitada: false })
    servirCon(servidor)

    await montarAdmin('/admin/catalogo/productos')

    const enlace = await screen.findByRole('link', { name: 'Iniciar sesión' })
    expect(enlace).toHaveAttribute('href', '/admin/login')
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    // No quedó en blanco: el layout se dibujó, sin ninguna sección protegida.
    expect(menuDeAdministracion()).toBeInTheDocument()
    expect(within(menuDeAdministracion()).queryAllByRole('link')).toHaveLength(0)
    // No reintenta ni una vez: una sola petición de sesión y una sola
    // renovación, sin el backoff por defecto de TanStack Query.
    expect(servidor.rutasPedidas('/auth/refresh')).toHaveLength(1)
    expect(servidor.rutasPedidas('/yo')).toHaveLength(1)
  })

  it('sin access token pero con la renovación aceptada, la página recargada recupera la sesión y no ofrece iniciar sesión', async () => {
    // El otro lado del caso anterior, y el que no hay que romper al cortar:
    // al recargar, el access token se perdió (vive solo en memoria, ADR-017)
    // pero la cookie `HttpOnly` del refresh sigue vigente. La sesión NO
    // terminó, así que `/yo` sí tiene que ir a la red: el 401 del primer
    // intento dispara la renovación y el reintento con el token nuevo trae
    // los permisos. Un corte que fallara rápido solo porque "no hay token"
    // dejaría al usuario sin sesión en cada recarga.
    const servidor = crearServidorDePrueba()
    servirCon(servidor)

    await montarAdmin('/admin/catalogo/productos')

    expect(await screen.findByRole('link', { name: 'Catálogo' })).toBeInTheDocument()
    const menu = menuDeAdministracion()
    expect(within(menu).getByRole('link', { name: 'Proveedores' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Iniciar sesión' })).not.toBeInTheDocument()
    // El 401 inicial (sin token) y el reintento con el token renovado: dos
    // peticiones y ni una más.
    expect(servidor.rutasPedidas('/auth/refresh')).toHaveLength(1)
    expect(servidor.rutasPedidas('/yo')).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------
// Servidor de prueba
// ---------------------------------------------------------------------

const PREFIJO_API = '/api/v1'

/** 401 de una ruta autenticada con usuario inactivo o token inválido: es el
 * mismo código que devuelve `core/seguridad.py` y
 * `identidad.service.obtener_yo` (ADR-028 D9.2-A). */
const SIN_AUTENTICAR = { title: 'No autenticado.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }

/** 401 de la renovación: `IDENTIDAD_REFRESH_TOKEN_INVALIDO`, el rechazo
 * genérico que también usa un usuario dado de baja (ADR-028). */
const REFRESH_INVALIDO = { title: 'El refresh token no es válido.', codigo: 'IDENTIDAD_REFRESH_TOKEN_INVALIDO' }

const PAGINA_VACIA = { items: [], cursor_siguiente: null }
const CATEGORIA_ID = '11111111-1111-4111-8111-111111111111'
const PRODUCTO_ID = '33333333-3333-4333-8333-333333333333'
const PRODUCTO = {
  id: PRODUCTO_ID,
  codigo: 'GAS-001',
  nombre: 'Gaseosa cola',
  categoria_id: CATEGORIA_ID,
  marca_id: null,
  unidad_base: 'unidad',
  alicuota_id: '22222222-2222-4222-8222-222222222222',
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}
const PRODUCTO_DETALLE = {
  ...PRODUCTO,
  proveedor_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  proveedor_nombre: 'Bodega Andina',
  presentaciones: [],
}
const DISPOSITIVO = {
  id: '44444444-4444-4444-8444-444444444444',
  nombre: 'Tablet del depósito',
  prefijo: 'DEP',
  estado: 'ACTIVO',
  ultimo_correlativo: 17,
  revocado_en: null,
}

/**
 * `fetch` de mentira con las dos reglas que alcanzan para este archivo: si
 * la sesión está habilitada y la petición lleva `Authorization`, responde
 * el cuerpo de la ruta; si no, responde 401. `/auth/refresh` responde según
 * su propio flag (la cookie puede revocar la sesión aunque el access token
 * siga pareciendo válido).
 */
function crearServidorDePrueba({
  sesionHabilitada = true,
  rol = 'GES',
}: { sesionHabilitada?: boolean; rol?: RolDePrueba } = {}) {
  const estado = { sesionHabilitada, refreshAceptada: sesionHabilitada }
  const rutasPedidas: string[] = []
  let tokensRenovados = 0

  const fetchMock = vi.fn((entrada: unknown, init?: RequestInit) => {
    const url = String(entrada)
    const ruta = url.startsWith(PREFIJO_API) ? url.slice(PREFIJO_API.length) : url
    rutasPedidas.push(ruta)
    const llevaToken = new Headers(init?.headers ?? {}).has('Authorization')

    if (ruta === '/auth/refresh') {
      if (!estado.refreshAceptada) {
        return Promise.resolve(respuesta(401, REFRESH_INVALIDO))
      }
      tokensRenovados += 1
      return Promise.resolve(respuesta(200, { access_token: `access-token-renovado-${tokensRenovados}` }))
    }

    if (!estado.sesionHabilitada || !llevaToken) {
      return Promise.resolve(respuesta(401, SIN_AUTENTICAR))
    }

    return Promise.resolve(respuesta(200, cuerpoDeRuta(ruta, rol)))
  })

  return {
    fetchMock,
    /** Lo que hace la 10.5 del script manual: `UPDATE usuario SET estado =
     * 'INACTIVO'`. A partir de acá ninguna ruta autenticada responde y la
     * renovación se rechaza. */
    darDeBajaAlUsuario(): void {
      estado.sesionHabilitada = false
      estado.refreshAceptada = false
    },
    rutasPedidas(ruta: string): string[] {
      return rutasPedidas.filter((pedida) => pedida === ruta)
    },
  }
}

function servirCon(servidor: ReturnType<typeof crearServidorDePrueba>): void {
  vi.stubGlobal('fetch', servidor.fetchMock)
}

function respuesta(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function cuerpoDeRuta(ruta: string, rol: RolDePrueba): unknown {
  if (ruta === '/yo') return yoDePrueba(rol)
  if (ruta === `/catalogo/productos/${PRODUCTO_ID}`) return PRODUCTO_DETALLE
  if (ruta === '/identidad/dispositivos') return [DISPOSITIVO]
  if (ruta.startsWith('/catalogo/productos')) return { items: [PRODUCTO], cursor_siguiente: null }
  if (ruta.startsWith('/proveedores')) return PAGINA_VACIA
  if (ruta.startsWith('/catalogo/categorias')) return PAGINA_VACIA
  if (ruta.startsWith('/catalogo/marcas')) return PAGINA_VACIA
  if (ruta.startsWith('/configuracion/alicuotas')) return PAGINA_VACIA
  throw new Error(`ruta inesperada en el servidor de prueba: ${ruta}`)
}

function menuDeAdministracion(): HTMLElement {
  return screen.getByRole('navigation', { name: /navegación de administración/i })
}

/**
 * Monta `AdminScreen` con la misma composición real que `AppRoutes`
 * (`/admin/*`): las rutas de `AdminScreen` son relativas al router, así que
 * sin este envoltorio `/admin/catalogo/productos` no resolvería
 * `catalogo/*` y el árbol quedaría vacío.
 */
async function montarAdmin(rutaInicial: string) {
  const { AdminScreen } = await import('../../../../src/areas/admin/AdminScreen')
  return render(
    <MemoryRouter initialEntries={[rutaInicial]}>
      <Routes>
        <Route path="/admin/*" element={<AdminScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}
