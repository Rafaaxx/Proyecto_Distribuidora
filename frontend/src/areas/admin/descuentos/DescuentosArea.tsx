import { NavLink, Route, Routes } from 'react-router-dom'

import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { DescuentosSinPermiso, SIN_PERMISO_DE_TOPES } from './DescuentosSinPermiso'
import { ReglaDetalleScreen } from './ReglaDetalleScreen'
import { ReglaFormScreen } from './ReglaFormScreen'
import { ReglasListScreen } from './ReglasListScreen'
import { TopesPorRolScreen } from './TopesPorRolScreen'

const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'

/**
 * Router del área de descuentos dentro de `/admin` (change 16, grupo 15). Se carga en diferido
 * desde `AdminScreen`, mismo criterio que `PreciosArea`. Una sola sección del menú, "Descuentos"
 * (`GESTIONAR_DESCUENTOS`, ADR-027), con dos entradas: "Reglas" y, a quien además tiene
 * `ADMIN_USUARIOS`, "Topes por rol". Sin el permiso los hijos no se montan y no se pide nada; el
 * servidor valida cada petición igual (SEG-06).
 */
export function DescuentosArea() {
  return (
    <SiTienePermiso permiso="GESTIONAR_DESCUENTOS" fallback={<DescuentosSinPermiso titulo="Descuentos" />}>
      <div className="flex flex-col gap-4">
        <nav className="flex items-center gap-4" aria-label="Descuentos">
          <NavLink to="/admin/descuentos" end className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}>
            Reglas
          </NavLink>
          <SiTienePermiso permiso="ADMIN_USUARIOS">
            <NavLink to="/admin/descuentos/topes" className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}>
              Topes por rol
            </NavLink>
          </SiTienePermiso>
        </nav>
        <Routes>
          <Route path="/" element={<ReglasListScreen />} />
          <Route path="/nueva" element={<ReglaFormScreen />} />
          <Route path="/:reglaId" element={<ReglaDetalleScreen />} />
          <Route path="/:reglaId/editar" element={<ReglaFormScreen />} />
          <Route
            path="/topes"
            element={
              <SiTienePermiso
                permiso="ADMIN_USUARIOS"
                fallback={<DescuentosSinPermiso titulo="Topes por rol" mensaje={SIN_PERMISO_DE_TOPES} />}
              >
                <TopesPorRolScreen />
              </SiTienePermiso>
            }
          />
        </Routes>
      </div>
    </SiTienePermiso>
  )
}

export default DescuentosArea
