import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { PageHeader } from '../../../components/ui/PageHeader'
import { veSaldosDeProveedores } from '../../../domain/reportes/permisos'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { AjustesPorMotivoReporte } from './AjustesPorMotivoReporte'
import { ObservacionesPorVendedorReporte } from './ObservacionesPorVendedorReporte'
import { RendicionesReporte } from './RendicionesReporte'
import { SaldosDeClientesReporte, SaldosDeProveedoresReporte } from './SaldosReporte'
import { VentasReporte } from './VentasReporte'

const TITULO = 'Reportes'

const CLASE_PESTANA_ACTIVA = 'border-b-2 border-primary px-1 pb-1 text-sm font-semibold text-primary'
const CLASE_PESTANA = 'px-1 pb-1 text-sm text-primary/70 hover:text-primary'

const clasePestana = ({ isActive }: { isActive: boolean }) => (isActive ? CLASE_PESTANA_ACTIVA : CLASE_PESTANA)

/**
 * La pestaña de saldos de proveedores solo existe con la regla compuesta de D8 = B; entrar por la URL sin ella no
 * muestra datos: vuelve a «Ventas» (el servidor igual responde 403, SEG-06).
 */
function SoloConSaldosDeProveedores({ children }: { children: React.ReactNode }) {
  const permisos = usePermisos()
  if (permisos.estado === 'cargando') return null
  if (!veSaldosDeProveedores(permisos.tiene)) return <Navigate to="/admin/reportes" replace />
  return <>{children}</>
}

/**
 * Sección «Reportes» de `/admin` (change 26, tareas 10.1, 10.2, 11.1 y 12.1 a 12.3; D11; `01` §19, ADR-027): una sola entrada del
 * menú con seis pestañas de solo lectura. La ve quien tiene `VER_REPORTES`; sin el permiso no se monta ninguna
 * pantalla y no se pide nada (SEG-06).
 */
export function ReportesArea() {
  const permisos = usePermisos()
  const conSaldosDeProveedores = veSaldosDeProveedores(permisos.tiene)

  return (
    <SiTienePermiso permiso="VER_REPORTES" fallback={<PageHeader titulo={TITULO} />}>
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <nav aria-label="Pestañas de reportes" className="flex flex-wrap gap-4 border-b border-border">
          <NavLink to="/admin/reportes" end className={clasePestana}>
            Ventas
          </NavLink>
          <NavLink to="/admin/reportes/rendiciones" className={clasePestana}>
            Rendiciones
          </NavLink>
          <NavLink to="/admin/reportes/saldos-clientes" className={clasePestana}>
            Saldos de clientes
          </NavLink>
          {conSaldosDeProveedores && (
            <NavLink to="/admin/reportes/saldos-proveedores" className={clasePestana}>
              Saldos de proveedores
            </NavLink>
          )}
          <NavLink to="/admin/reportes/observaciones" className={clasePestana}>
            Observaciones por vendedor
          </NavLink>
          <NavLink to="/admin/reportes/ajustes" className={clasePestana}>
            Ajustes por motivo
          </NavLink>
        </nav>
        <Routes>
          <Route path="/" element={<VentasReporte />} />
          <Route path="/rendiciones" element={<RendicionesReporte />} />
          <Route path="/saldos-clientes" element={<SaldosDeClientesReporte />} />
          <Route
            path="/saldos-proveedores"
            element={
              <SoloConSaldosDeProveedores>
                <SaldosDeProveedoresReporte />
              </SoloConSaldosDeProveedores>
            }
          />
          <Route path="/observaciones" element={<ObservacionesPorVendedorReporte />} />
          <Route path="/ajustes" element={<AjustesPorMotivoReporte />} />
        </Routes>
      </main>
    </SiTienePermiso>
  )
}

export default ReportesArea
