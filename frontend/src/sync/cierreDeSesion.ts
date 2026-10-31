import { apiFetch } from '../lib/api/httpClient'
import { limpiarAccessToken } from '../lib/auth/tokenStore'
import { borrarSesionLocal } from '../lib/sesionLocal/sesionLocal'

/**
 * Cerrar sesión en el dispositivo (change 21, `design.md` D16; `02` §12.3; ADR-017). Requiere
 * conexión: revoca la sesión del dispositivo en el servidor y recién entonces borra la sesión
 * local, el PIN y los datos maestros (las operaciones pendientes y el `dispositivo_id` quedan).
 */
export type ResultadoCierre = 'cerrada' | 'sin_conexion' | 'error'

export async function cerrarSesionDelDispositivo(): Promise<ResultadoCierre> {
  if (!navigator.onLine) return 'sin_conexion'

  let respuesta: Response
  try {
    respuesta = await apiFetch('/auth/logout', { method: 'POST' })
  } catch {
    return 'sin_conexion'
  }

  // 401: el servidor ya no reconoce esta sesión; no hay nada que revocar y seguir mostrando la
  // sesión local sería peor. Cualquier otra falla deja todo como estaba.
  if (!respuesta.ok && respuesta.status !== 401) return 'error'

  await borrarSesionLocal()
  limpiarAccessToken()
  return 'cerrada'
}
