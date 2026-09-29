import type { CodigoPermiso } from '../../domain/identidad/permisos'

/**
 * Secciones del menú de `/admin` (tarea 7.1, `design.md` D5-A, **B3**).
 *
 * Es la **única** lista de secciones: el menú (`AdminLayout`) y la ruta
 * índice `/admin/inicio` (`AdminInicio`) la consultan, así que agregar una
 * pantalla de administración en el change 07 se declara en un solo lugar
 * y el menú y el aterrizaje no pueden desincronizarse.
 *
 * - El **orden** es el del menú y decide a dónde lleva `/admin/inicio`:
 *   Catálogo, Proveedores, Dispositivos (D5-A: "la primera sección
 *   permitida, en el orden del menú").
 * - `permiso` es el que el usuario tiene que tener en la consulta de
 *   sesión (`GET /api/v1/yo`) para ver la sección, según `01-dominio.md`
 *   §19.
 * - `ruta` es **absoluta** (`/admin/...`), nunca relativa: la tarea 10.8
 *   del change 05 fijo que un `to` relativo se resolvía contra el
 *   segmento en el que estaba parado quien navega
 *   (`/admin/dispositivos/catalogo` en vez de `/admin/catalogo`).
 *
 * Ocultar una sección es una comodidad de la interfaz: el servidor sigue
 * validando cada petición (SEG-06, ADR-027).
 */
export interface SeccionAdmin {
  ruta: string
  etiqueta: string
  permiso: CodigoPermiso
}

export const SECCIONES: readonly SeccionAdmin[] = [
  { ruta: '/admin/catalogo', etiqueta: 'Catálogo', permiso: 'GESTIONAR_CATALOGO' },
  { ruta: '/admin/proveedores', etiqueta: 'Proveedores', permiso: 'GESTIONAR_PROVEEDORES' },
  { ruta: '/admin/clientes', etiqueta: 'Clientes', permiso: 'GESTIONAR_CLIENTES' },
  { ruta: '/admin/dispositivos', etiqueta: 'Dispositivos', permiso: 'GESTIONAR_DISPOSITIVOS' },
]

/** Predicado de permiso de `usePermisos().tiene`. */
export type TienePermiso = (permiso: CodigoPermiso) => boolean

/**
 * Secciones que el usuario puede usar, en el orden de `SECCIONES`.
 * Falla cerrada sin trabajo extra: `tiene` ya devuelve `false` mientras
 * `/yo` está pendiente y ante un error (`design.md` D3-A, B1), así que
 * con la consulta pendiente o fallida esta lista viene vacía y no
 * aparece ninguna sección protegida.
 */
export function seccionesPermitidas(tiene: TienePermiso): SeccionAdmin[] {
  return SECCIONES.filter((seccion) => tiene(seccion.permiso))
}

/**
 * Primera sección permitida, la que muestra `/admin/inicio` (**B3**).
 * `undefined` cuando el usuario no tiene ninguna.
 */
export function primeraSeccionPermitida(tiene: TienePermiso): SeccionAdmin | undefined {
  return seccionesPermitidas(tiene)[0]
}
