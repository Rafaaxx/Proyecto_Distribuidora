import { NavLink, Outlet } from 'react-router-dom'

/**
 * Layout mínimo de `/admin` (tarea 10.1, `design.md` D10): encabezado con
 * navegación a Catálogo y Dispositivos, `<Outlet />` para la pantalla
 * activa. No envuelve `login` -- antes de autenticarse no hay nada que
 * navegar.
 *
 * Tarea 10.8: los `to` de estos `NavLink` son absolutos (`/admin/...`), no
 * relativos. Con `to="catalogo"` (relativo), al estar parado en
 * `/admin/dispositivos` React Router lo resolvía contra ese segmento y
 * navegaba a `/admin/dispositivos/catalogo` en vez de `/admin/catalogo`
 * (reproducido en navegador real tras iniciar sesión, que redirige a
 * `/admin/dispositivos`); lo mismo en sentido inverso desde
 * `/admin/catalogo/*`. Una ruta absoluta no depende de dónde esté parado
 * quien navega.
 */
const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'

export function AdminLayout() {
  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="border-b border-border bg-surface px-4 py-3">
        <nav className="flex items-center gap-4" aria-label="Navegación de administración">
          <NavLink to="/admin/catalogo" className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}>
            Catálogo
          </NavLink>
          <NavLink to="/admin/proveedores" className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}>
            Proveedores
          </NavLink>
          <NavLink
            to="/admin/dispositivos"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Dispositivos
          </NavLink>
        </nav>
      </header>
      <div className="p-4">
        <Outlet />
      </div>
    </div>
  )
}

export default AdminLayout
