import { useEffect, useState } from 'react'
import { Navigate, NavLink, Outlet, useLocation } from 'react-router-dom'

import { Alert } from '../../components/ui/Alert'
import { Boton } from '../../components/ui/Button'
import type { Yo } from '../../features/identidad/api'
import { ofreceMiPin } from '../../domain/identidad/pin'
import { contadorDelMenu } from '../../domain/revision/aviso'
import { useResumenDePendientes } from '../../features/revision/hooks'
import { SECCIONES, seccionesPermitidas } from '../../features/identidad/secciones'
import { useCerrarSesion } from '../../features/identidad/useCerrarSesion'
import { usePermisos } from '../../features/identidad/usePermisos'
import { useTituloDePagina } from '../../lib/useTituloDePagina'

const CLASE_ENLACE_BASE =
  'flex min-h-11 items-center gap-2 rounded-md border-l-4 px-3 py-2 text-lg transition-[color,background-color,transform] duration-150 motion-reduce:transition-none'
const CLASE_ENLACE_ACTIVO = `${CLASE_ENLACE_BASE} border-primary bg-primary/10 font-semibold text-primary`
const CLASE_ENLACE = `${CLASE_ENLACE_BASE} border-transparent font-medium text-primary/80 hover:translate-x-1 hover:border-primary/40 hover:bg-surface-muted hover:text-primary motion-reduce:hover:translate-x-0`
const RUTA_AYUDA = '/admin/ayuda'
const RUTA_LOGIN = '/admin/login'
const RUTA_MI_PIN = '/admin/mi-pin'
const RUTA_MI_CONTRASENA = '/admin/mi-contrasena'
const RUTA_REVISION = '/admin/revision'
const MENSAJE_SIN_PERMISOS = 'No se pudieron obtener tus permisos.'
const ID_MENU = 'menu-lateral'
const RUTA_INICIO = '/admin/inicio'

/** Páginas fuera de `SECCIONES` que también tienen enlace en el menú lateral. */
const TITULOS_EXTRA: readonly (readonly [ruta: string, titulo: string])[] = [
  [RUTA_INICIO, 'Inicio'],
  [RUTA_AYUDA, 'Ayuda'],
  [RUTA_MI_PIN, 'Mi PIN'],
  [RUTA_MI_CONTRASENA, 'Mi contraseña'],
]

/**
 * Título de la pestaña según la sección activa del menú (`SECCIONES` más las páginas extra).
 * Sin coincidencia (la 404) devuelve `null`: la pantalla hija fija su propio título.
 */
function tituloDeSeccion(pathname: string): string | null {
  const coincide = (ruta: string) => pathname === ruta || pathname.startsWith(`${ruta}/`)
  const seccion = SECCIONES.find((s) => coincide(s.ruta))
  if (seccion) return seccion.etiqueta
  const extra = TITULOS_EXTRA.find(([ruta]) => coincide(ruta))
  return extra ? extra[1] : null
}

function claseDeEnlace({ isActive }: { isActive: boolean }): string {
  return isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE
}

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
 * Layout de `/admin`: barra superior con el botón ☰, menú lateral por permiso y `<Outlet />` para
 * la pantalla activa. No envuelve `login` -- antes de autenticarse no hay nada que navegar.
 *
 * El menú va oculto en todos los tamaños de pantalla: se abre con el botón ☰ como panel
 * superpuesto y se cierra al elegir una sección, al tocar el fondo oscurecido o con Escape. El
 * panel siempre está en el DOM; el CSS lo oculta con `invisible`, que además lo saca del foco del
 * teclado y de los lectores de pantalla.
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
 * Tarea 7.5 (**B4**): en la barra superior, "{usuario} · {organización} · {rol}".
 *
 * Tarea 7.4 (**B1**, `design.md` D3-A): si la consulta de sesión falla, el
 * layout avisa y ofrece **Reintentar**; si falla con 401 -- o sea, la
 * renovación del access token ya fue rechazada y la sesión terminó
 * (ADR-017) -- redirige a `/admin/login`, porque sin token un reintento solo
 * vuelve a fallar. No redirige mientras haya una consulta de `/yo` en vuelo:
 * justo después de iniciar sesión el error viejo sigue en caché hasta que
 * llega la respuesta nueva.
 */
export function AdminLayout() {
  const permisos = usePermisos()
  const secciones = seccionesPermitidas(permisos.tiene)
  const sesionTerminada = permisos.error?.status === 401
  const identificacion = identificacionDeSesion(permisos.yo)
  // Change 25 (D5, CRE-09): el total pendiente junto a «Revisión»; sin el permiso no se pide nada (SEG-06).
  const resumen = useResumenDePendientes(permisos.tiene('REVISAR_OBSERVACIONES'))
  const pendientes = contadorDelMenu(resumen.data)
  const [abierto, setAbierto] = useState(false)
  const cierre = useCerrarSesion()
  useTituloDePagina(tituloDeSeccion(useLocation().pathname))

  useEffect(() => {
    if (!abierto) return undefined
    const alTeclear = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') setAbierto(false)
    }
    document.addEventListener('keydown', alTeclear)
    return () => document.removeEventListener('keydown', alTeclear)
  }, [abierto])

  if (sesionTerminada && !permisos.actualizando) {
    return <Navigate to={RUTA_LOGIN} replace />
  }

  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="flex items-center gap-3 border-b-2 border-border bg-surface px-4 py-2">
        <Boton
          variante="secundario"
          aria-label="Menú"
          aria-expanded={abierto}
          aria-controls={ID_MENU}
          onClick={() => setAbierto((valor) => !valor)}
        >
          <span aria-hidden="true" className="text-xl leading-none">
            ☰
          </span>
        </Boton>
        <span className="shrink-0 text-base font-semibold text-primary">Administración</span>
        {identificacion && <span className="min-w-0 truncate text-sm text-primary/70">{identificacion}</span>}
      </header>

      {abierto && (
        <div
          data-testid="fondo-del-menu"
          aria-hidden="true"
          className="fixed inset-0 z-20 bg-black/50"
          onClick={() => setAbierto(false)}
        />
      )}

      {/* Un clic en cualquier enlace del panel (elegir una sección) lo cierra. */}
      <aside
        id={ID_MENU}
        onClick={(evento) => {
          if ((evento.target as HTMLElement).closest('a')) setAbierto(false)
        }}
        className={`fixed inset-y-0 left-0 z-30 flex w-72 max-w-[85vw] flex-col gap-4 overflow-y-auto border-r-2 border-border bg-surface p-4 shadow-lg transition-[transform,visibility] ${
          abierto ? 'visible translate-x-0' : 'invisible -translate-x-full'
        }`}
      >
        <nav className="flex flex-col gap-1" aria-label="Navegación de administración">
          {secciones.map((seccion) => (
            <NavLink key={seccion.ruta} to={seccion.ruta} className={claseDeEnlace}>
              {seccion.etiqueta}
              {seccion.ruta === RUTA_REVISION && pendientes !== null && (
                <>
                  {' '}
                  <span className="rounded-full bg-danger px-2 py-0.5 text-xs font-semibold text-danger-foreground">
                    {pendientes}
                  </span>
                </>
              )}
            </NavLink>
          ))}
          {/* Ayuda (change 16b, D6 = A): sin datos ni permisos, la ve todo usuario con sesión
              confirmada; falla cerrada igual que las secciones mientras /yo está pendiente o falló. */}
          {permisos.yo && (
            <NavLink to={RUTA_AYUDA} className={claseDeEnlace}>
              Ayuda
            </NavLink>
          )}
        </nav>

        <div className="mt-auto flex flex-col gap-3 border-t-2 border-border pt-4">
          {/* "Mi cuenta" (change 20b, D20): "Mi PIN" y "Mi contraseña". La ve todo usuario con sesión
              confirmada (falla cerrada como Ayuda); "Mi PIN" conserva su regla (change 18b, D21 parte B):
              solo con algún permiso de autorización. */}
          {permisos.yo && (
            <nav className="flex flex-col gap-1" aria-label="Mi cuenta">
              <span className="px-3 text-sm font-semibold text-primary">Mi cuenta</span>
              {ofreceMiPin(permisos.tiene) && (
                <NavLink to={RUTA_MI_PIN} className={claseDeEnlace}>
                  Mi PIN
                </NavLink>
              )}
              <NavLink to={RUTA_MI_CONTRASENA} className={claseDeEnlace}>
                Mi contraseña
              </NavLink>
            </nav>
          )}
          <Boton variante="peligro" disabled={cierre.cerrando} onClick={() => void cierre.cerrar()}>
            {cierre.cerrando ? 'Cerrando…' : 'Cerrar sesión'}
          </Boton>
          {cierre.error && <Alert>{cierre.error}</Alert>}
        </div>
      </aside>

      {permisos.estado === 'error' && (
        <Alert className="m-4 flex flex-wrap items-center gap-2">
          <span>{MENSAJE_SIN_PERMISOS}</span>
          <Boton variante="secundario" onClick={permisos.reintentar}>
            Reintentar
          </Boton>
        </Alert>
      )}
      <div className="p-4">
        <Outlet />
      </div>
    </div>
  )
}

export default AdminLayout
