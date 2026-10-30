import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { AlicuotasScreen } from './AlicuotasScreen'
import { ConfiguracionFiscalScreen } from './ConfiguracionFiscalScreen'
import { DatosDeLaOrganizacionScreen } from './DatosDeLaOrganizacionScreen'
import { DescuentoYCreditoScreen } from './DescuentoYCreditoScreen'
import type { CodigoPermiso } from '../../../domain/identidad/permisos'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { ListaPredeterminadaScreen } from './ListaPredeterminadaScreen'
import { MediosPagoScreen } from './MediosPagoScreen'
import { MotivosScreen } from './MotivosScreen'
import { NotaDeVentaScreen } from './NotaDeVentaScreen'
import { RedondeoPorDefectoScreen } from './RedondeoPorDefectoScreen'

const CLASE_ENLACE_ACTIVO = 'font-semibold text-primary'
const CLASE_ENLACE = 'text-primary/70 hover:text-primary'

/** Quien puede ver "Lista predeterminada": los mismos permisos que su GET (change 20c, 14.2). */
const PERMISOS_DE_LISTAS: readonly CodigoPermiso[] = ['ADMIN_CONFIGURACION', 'GESTIONAR_LISTAS', 'PUBLICAR_LISTAS']

/** Ruta índice: "Fiscal" para quien administra la configuración; si no, la pestaña de listas. */
function IndiceDeConfiguracion() {
  const permisos = usePermisos()
  if (permisos.estado === 'cargando') return null
  return <Navigate to={permisos.tiene('ADMIN_CONFIGURACION') ? 'fiscal' : 'lista-predeterminada'} replace />
}

/**
 * Router del área de configuración dentro de `/admin` (change 11b, tarea 7.4; change 13, tarea
 * 13.5; change 18b, tarea 14.1). Se carga en diferido desde `AdminScreen`. Pantallas:
 * `/admin/configuracion/fiscal`, `lista-predeterminada`, `medios-pago`, `descuento-y-credito`, `nota-de-venta`, `organizacion` (change 20, D15), `motivos`, `alicuotas` y `redondeo` (change 20c, D12); la
 * ruta índice lleva a la fiscal (o a la lista predeterminada si la sesión solo tiene permisos de
 * listas). Change 20c, 14.2: cada pestaña se ofrece solo con el permiso de su pantalla.
 */
export function ConfiguracionArea() {
  return (
    <div className="flex flex-col gap-4">
      <nav aria-label="Secciones de configuración" className="flex gap-4 text-sm">
        <SiTienePermiso permiso="ADMIN_CONFIGURACION">
          <NavLink
            to="/admin/configuracion/fiscal"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Fiscal
          </NavLink>
        </SiTienePermiso>
        <SiTienePermiso permiso={PERMISOS_DE_LISTAS}>
          <NavLink
            to="/admin/configuracion/lista-predeterminada"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Lista predeterminada
          </NavLink>
        </SiTienePermiso>
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
          <NavLink
            to="/admin/configuracion/motivos"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Motivos
          </NavLink>
          <NavLink
            to="/admin/configuracion/alicuotas"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Alícuotas de IVA
          </NavLink>
          <NavLink
            to="/admin/configuracion/redondeo"
            className={({ isActive }) => (isActive ? CLASE_ENLACE_ACTIVO : CLASE_ENLACE)}
          >
            Redondeo por defecto
          </NavLink>
        </SiTienePermiso>
      </nav>
      <Routes>
        <Route path="/" element={<IndiceDeConfiguracion />} />
        <Route path="fiscal" element={<ConfiguracionFiscalScreen />} />
        <Route path="lista-predeterminada" element={<ListaPredeterminadaScreen />} />
        <Route path="medios-pago" element={<MediosPagoScreen />} />
        <Route path="descuento-y-credito" element={<DescuentoYCreditoScreen />} />
        <Route path="nota-de-venta" element={<NotaDeVentaScreen />} />
        <Route path="organizacion" element={<DatosDeLaOrganizacionScreen />} />
        <Route path="motivos" element={<MotivosScreen />} />
        <Route path="alicuotas" element={<AlicuotasScreen />} />
        <Route path="redondeo" element={<RedondeoPorDefectoScreen />} />
      </Routes>
    </div>
  )
}

export default ConfiguracionArea
