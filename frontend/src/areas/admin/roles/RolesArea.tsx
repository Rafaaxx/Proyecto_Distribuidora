import { NavLink, Route, Routes } from 'react-router-dom'

import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { PinAutorizacionScreen } from './PinAutorizacionScreen'
import { RolesScreen } from './RolesScreen'

const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'

/**
 * Router del área "Roles y permisos" dentro de `/admin` (change 17b, tarea 9.1; change 18b, tarea
 * 14.2). Se carga en diferido desde `AdminScreen`. Dos pestañas, ambas con `ADMIN_USUARIOS`:
 * `/admin/roles` (permisos de cada rol) y `/admin/roles/pin` (PIN de autorización de los
 * supervisores).
 */
export function RolesArea() {
  return (
    <div className="flex flex-col gap-4">
      <SiTienePermiso permiso="ADMIN_USUARIOS">
        <nav aria-label="Secciones de roles" className="flex gap-4 text-sm">
          <NavLink to="/admin/roles" end className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}>
            Roles y permisos
          </NavLink>
          <NavLink to="/admin/roles/pin" className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}>
            PIN de autorización
          </NavLink>
        </nav>
      </SiTienePermiso>
      <Routes>
        <Route path="/" element={<RolesScreen />} />
        <Route path="pin" element={<PinAutorizacionScreen />} />
      </Routes>
    </div>
  )
}

export default RolesArea
