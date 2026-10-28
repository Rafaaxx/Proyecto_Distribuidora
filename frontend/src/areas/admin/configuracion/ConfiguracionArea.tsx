import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { ConfiguracionFiscalScreen } from './ConfiguracionFiscalScreen'
import { DatosDeLaOrganizacionScreen } from './DatosDeLaOrganizacionScreen'
import { DescuentoYCreditoScreen } from './DescuentoYCreditoScreen'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ListaPredeterminadaScreen } from './ListaPredeterminadaScreen'
import { MediosPagoScreen } from './MediosPagoScreen'
import { NotaDeVentaScreen } from './NotaDeVentaScreen'

const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'

/**
 * Router del área de configuración dentro de `/admin` (change 11b, tarea 7.4; change 13, tarea
 * 13.5; change 18b, tarea 14.1). Se carga en diferido desde `AdminScreen`. Pantallas:
 * `/admin/configuracion/fiscal`, `lista-predeterminada`, `medios-pago`, `descuento-y-credito`, `nota-de-venta` y `organizacion` (change 20, D15); la
 * ruta índice lleva a la fiscal.
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
        <SiTienePermiso permiso="ADMIN_CONFIGURACION">
          <NavLink
            to="/admin/configuracion/medios-pago"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Medios de pago
          </NavLink>
          <NavLink
            to="/admin/configuracion/descuento-y-credito"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Descuento y crédito
          </NavLink>
          <NavLink
            to="/admin/configuracion/nota-de-venta"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Nota de venta
          </NavLink>
          <NavLink
            to="/admin/configuracion/organizacion"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Datos de la organización
          </NavLink>
        </SiTienePermiso>
      </nav>
      <Routes>
        <Route path="/" element={<Navigate to="fiscal" replace />} />
        <Route path="fiscal" element={<ConfiguracionFiscalScreen />} />
        <Route path="lista-predeterminada" element={<ListaPredeterminadaScreen />} />
        <Route path="medios-pago" element={<MediosPagoScreen />} />
        <Route path="descuento-y-credito" element={<DescuentoYCreditoScreen />} />
        <Route path="nota-de-venta" element={<NotaDeVentaScreen />} />
        <Route path="organizacion" element={<DatosDeLaOrganizacionScreen />} />
      </Routes>
    </div>
  )
}

export default ConfiguracionArea
