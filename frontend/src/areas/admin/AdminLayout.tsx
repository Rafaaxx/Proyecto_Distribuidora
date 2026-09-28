import { Link, NavLink, Outlet } from 'react-router-dom'

import { Alert } from '../../components/ui/Alert'
import { Boton } from '../../components/ui/Button'
import type { Yo } from '../../features/identidad/api'
import { seccionesPermitidas } from '../../features/identidad/secciones'
import { usePermisos } from '../../features/identidad/usePermisos'

const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'
const MENSAJE_SIN_PERMISOS = 'No se pudieron obtener tus permisos.'

/**
 * "{usuario} · {organización} · {rol}" (tarea 7.5, **B4**, `design.md`
 * D6-A). Los tres nombres salen de `GET /api/v1/yo`. Vacío mientras la
 * consulta está pendiente o si falló: el encabezado no inventa datos de la
 * sesión que todavía no conoce.
 */
function identificacionDeSesion(yo: Yo | undefined): string {
  if (!yo) {
    return ''
  }
  return [yo.usuario.nombre, yo.organizacion.nombre, yo.rol.nombre].join(' · ')
}

/**
 * Layout de `/admin`: encabezado con el menú por permiso, `<Outlet />` para
 * la pantalla activa. No envuelve `login` -- antes de autenticarse no hay
 * nada que navegar.
 *
 * El menú se arma desde la lista única de secciones
 * (`features/identidad/secciones.ts`, tarea 7.1) filtrada con
 * `usePermisos().tiene` (tarea 7.3, `design.md` D3-A / D5-A, ADR-027),
 * que es la consulta `['yo']` de `GET /api/v1/yo`: la misma fuente de
 * permisos que autoriza en el servidor. Ocultar una sección es una
 * comodidad; el servidor sigue validando cada petición (SEG-06).
 *
 * Falla cerrada (**B1**): `tiene` devuelve `false` mientras `/yo` está
 * pendiente y ante un error, así que en ninguno de los dos estados
 * aparecen secciones sin confirmar.
 *
 * Tarea 10.8 del change 05: los `to` de estos `NavLink` son absolutos
 * (`/admin/...`), no relativos. Con `to="catalogo"` (relativo), al estar
 * parado en `/admin/dispositivos` React Router lo resolvía contra ese
 * segmento y navegaba a `/admin/dispositivos/catalogo` en vez de
 * `/admin/catalogo` (reproducido en navegador real tras iniciar sesión);
 * lo mismo en sentido inverso desde `/admin/catalogo/*`. Una ruta
 * absoluta no depende de dónde esté parado quien navega. La lista de
 * secciones de `secciones.ts` ya viene con rutas absolutas.
 *
 * Tarea 7.5 (**B4**): a la derecha del menú, "{usuario} · {organización}
 * · {rol}".
 *
 * Tarea 7.4 (**B1**, `design.md` D3-A): si la consulta de sesión falla, el
 * encabezado avisa y ofrece **Reintentar**; si falla con 401 -- o sea, la
 * renovación del access token ya fue rechazada y la sesión terminó
 * (ADR-017) -- ofrece ir a iniciar sesión en vez de reintentar, porque sin
 * token un reintento solo vuelve a fallar.
 */
export function AdminLayout() {
  const permisos = usePermisos()
  const secciones = seccionesPermitidas(permisos.tiene)
  const sesionTerminada = permisos.error?.status === 401
  const identificacion = identificacionDeSesion(permisos.yo)

  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="border-b border-border bg-surface px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <nav className="flex items-center gap-4" aria-label="Navegación de administración">
            {secciones.map((seccion) => (
              <NavLink
                key={seccion.ruta}
                to={seccion.ruta}
                className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
              >
                {seccion.etiqueta}
              </NavLink>
            ))}
          </nav>

          {identificacion && <p className="text-sm text-primary/70">{identificacion}</p>}
        </div>

        {permisos.estado === 'error' && (
          <Alert className="mt-3 flex flex-wrap items-center gap-2">
            <span>{MENSAJE_SIN_PERMISOS}</span>
            {sesionTerminada ? (
              <Link to="/admin/login" className="font-medium underline">
                Iniciar sesión
              </Link>
            ) : (
              <Boton variante="secundario" onClick={permisos.reintentar}>
                Reintentar
              </Boton>
            )}
          </Alert>
        )}
      </header>
      <div className="p-4">
        <Outlet />
      </div>
    </div>
  )
}

export default AdminLayout
