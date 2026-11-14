import { apiFetch } from '../../lib/api/httpClient'
import { limpiarAccessToken } from '../../lib/auth/tokenStore'

/**
 * Cerrar sesión en `/admin`: revoca la sesión en el servidor y recién entonces olvida el access
 * token en memoria (ADR-017). A diferencia de `/ruta` (`sync/cierreDeSesion.ts`), acá no hay
 * sesión local, PIN ni datos descargados que borrar: nada de Dexie ni operaciones pendientes.
 *
 * `limpiarAccessToken()` deja además la sesión marcada como terminada, así la pantalla de
 * login no la "recupera" con la cookie de refresh que el servidor acaba de revocar.
 */
export type ResultadoCierreAdmin = 'cerrada' | 'sin_conexion' | 'error'

export async function cerrarSesionAdmin(): Promise<ResultadoCierreAdmin> {
  let respuesta: Response
  try {
    respuesta = await apiFetch('/auth/logout', { method: 'POST' })
  } catch {
    return 'sin_conexion'
  }

  // 401: el servidor ya no reconoce esta sesión; no hay nada que revocar. Cualquier otra falla
  // deja todo como estaba para que el usuario pueda reintentar.
  if (!respuesta.ok && respuesta.status !== 401) return 'error'

  limpiarAccessToken()
  return 'cerrada'
}
