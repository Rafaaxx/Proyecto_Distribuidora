import { Navigate } from 'react-router-dom'

import { primeraSeccionPermitida } from '../../features/identidad/secciones'
import { usePermisos } from '../../features/identidad/usePermisos'

/**
 * Ruta índice de `/admin` (`/admin/inicio`, tarea 7.6, `design.md` D5-A,
 * **B3**): es adonde lleva el login. No es una pantalla con datos propios,
 * sino el punto que decide a qué sección lleva a cada usuario.
 *
 * Antes de `/admin/dispositivos` el login mandaba a todo el mundo a
 * Dispositivos, así que un usuario de Administración o un Vendedor veían
 * "No tenés permiso" apenas entraban (`01` §19: solo Administración y
 * Supervisor tienen `GESTIONAR_DISPOSITIVOS`). Ahora la ruta espera la
 * consulta de sesión y salta a la primera sección permitida, en el orden
 * de `features/identidad/secciones.ts` -- la misma lista que arma el menú,
 * así que el aterrizaje no puede desincronizarse de él.
 *
 * Falla cerrada (**B1**): mientras `/yo` está pendiente no salta a ninguna
 * parte, y si la consulta falla no afirma que el usuario no tiene
 * secciones (informar eso sería mentir: lo que no se sabe es si las tiene).
 * El aviso con **Reintentar** o el enlace a iniciar sesión lo muestra el
 * layout, que envuelve esta ruta.
 */
const SIN_SECCIONES = 'Tu usuario no tiene secciones de administración disponibles'

export function AdminInicio() {
  const permisos = usePermisos()

  if (permisos.estado === 'cargando') {
    return <p className="text-sm text-primary/70">Cargando…</p>
  }

  if (permisos.estado === 'error') {
    return null
  }

  const primera = primeraSeccionPermitida(permisos.tiene)

  if (!primera) {
    return <p className="text-sm text-primary/70">{SIN_SECCIONES}</p>
  }

  return <Navigate to={primera.ruta} replace />
}

export default AdminInicio
