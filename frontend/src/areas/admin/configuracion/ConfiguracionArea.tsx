import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { ConfiguracionFiscalScreen } from './ConfiguracionFiscalScreen'
import { ListaPredeterminadaScreen } from './ListaPredeterminadaScreen'

const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'

/**
 * Router del área de configuración dentro de `/admin` (change 11b, tarea 7.4; change 13, tarea
 * 13.5). Se carga en diferido desde `AdminScreen`. Dos pantallas: `/admin/configuracion/fiscal` y
 * `/admin/configuracion/lista-predeterminada`; la ruta índice lleva a la fiscal.
 */
export function ConfiguracionArea() {
  return (
    <div className="flex flex-col gap-4">
      <nav aria-label="Secciones de configuración" className="flex gap-4 text-sm">
        <NavLink
          to="/admin/configuracion/fiscal"
          className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
        >
          Fiscal
        </NavLink>
        <NavLink
          to="/admin/configuracion/lista-predeterminada"
          className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
        >
          Lista predeterminada
        </NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Navigate to="fiscal" replace />} />
        <Route path="fiscal" element={<ConfiguracionFiscalScreen />} />
        <Route path="lista-predeterminada" element={<ListaPredeterminadaScreen />} />
      </Routes>
    </div>
  )
}

export default ConfiguracionArea
