/**
 * Predicado de reintento para mutaciones de escritura (tarea 14.2,
 * corrección posterior a la verificación manual de 13.5).
 *
 * TanStack Query reintenta una mutación fallida volviendo a invocar
 * `mutationFn` con las MISMAS variables. `useMutacionConOperationId` (en
 * `features/proveedores/useMutaciones.ts` y
 * `features/catalogo/useMutacionesCatalogo.ts`) aprovecha eso para
 * reenviar exactamente el mismo `Operation-Id` en el reintento, de modo
 * que el bus de comandos lo trate como la MISMA operación (INV-06,
 * `design.md` D10). Ese mecanismo solo tiene sentido frente a un error de
 * RED: la petición nunca llegó a producir una respuesta HTTP, así que no
 * hay ninguna operación ya resuelta por el servidor que se esté
 * duplicando.
 *
 * Antes de esta corrección, `retry: REINTENTOS_POR_ERROR_DE_RED` (un
 * número fijo, sin predicado) reintentaba CUALQUIER rechazo, incluido un
 * error de dominio con una respuesta HTTP real (409 `NOMBRE_DUPLICADO`,
 * 422 de validación, …). Bug observado en la verificación manual de la
 * tarea 13.5: un envío con un nombre duplicado mandaba 3 POST idénticos
 * al servidor, los tres rechazados con 409, en vez de fallar una sola vez.
 *
 * Los errores de dominio que traducen una respuesta HTTP no-ok
 * (`ErrorDeProveedores`, `ErrorDeCatalogo`, y sus subclases de permiso)
 * siempre tienen un `codigo` propio (`features/proveedores/errores.ts`,
 * `features/catalogo/errores.ts`). Un error de red -- una falla de
 * `fetch` en sí, antes de que exista una `Response` -- nunca lo tiene
 * (t. ej. `TypeError: Failed to fetch`). Este módulo se apoya en esa
 * distinción estructural (`codigo` presente o no) en vez de importar las
 * clases de error de cada feature: `lib/api` es infraestructura
 * compartida y no debe depender de módulos de negocio ajenos (`CLAUDE.md`
 * §4, "un módulo usa a otro solo a través de su `service.py`" -- mismo
 * criterio aplicado al frontend).
 */

export const REINTENTOS_POR_ERROR_DE_RED = 2

function tieneCodigoDeDominio(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'codigo' in error &&
    typeof (error as { codigo?: unknown }).codigo === 'string'
  )
}

/**
 * Un error es "de red" cuando NO representa una respuesta HTTP ya
 * recibida (no tiene `codigo` de dominio). Incluye la falla de `fetch`
 * en sí (sin conexión, DNS, CORS bloqueado, etc.) y cualquier rechazo que
 * no haya pasado por la traducción de `errorDesdeRespuesta`.
 */
export function esErrorDeRed(error: unknown): boolean {
  return !tieneCodigoDeDominio(error)
}

/**
 * Decide si TanStack Query debe reintentar la mutación. `intentos` es el
 * `failureCount` que TanStack le pasa a `retry`: fallos ANTERIORES al
 * actual (arranca en 0 en la primera falla), el mismo criterio que su
 * `retry: n` numérico (`failureCount < n`) -- así se hacen como máximo
 * `REINTENTOS_POR_ERROR_DE_RED` reintentos.
 */
export function debeReintentar(intentos: number, error: unknown): boolean {
  return esErrorDeRed(error) && intentos < REINTENTOS_POR_ERROR_DE_RED
}
