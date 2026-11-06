import { NavLink, Route, Routes } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { PageHeader } from '../../../components/ui/PageHeader'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ObservacionesScreen } from './ObservacionesScreen'
import { RechazadasScreen } from './RechazadasScreen'

const TITULO = 'Revisión'
export const SIN_PERMISO_DE_REVISION = 'No tenés permiso para ver la revisión.'

const CLASE_PESTANA_ACTIVA = 'border-b-2 border-primary px-1 pb-1 text-sm font-semibold text-primary'
const CLASE_PESTANA = 'px-1 pb-1 text-sm text-primary/70 hover:text-primary'

/**
 * Área «Revisión» de `/admin` (change 25, tareas 13.2 y 14.1; D11; `01` §19): una sola sección del menú, con dos
 * pestañas, «Observaciones» y «Rechazadas». La ve quien tiene `REVISAR_OBSERVACIONES`; sin el permiso las
 * pantallas no se montan y no piden nada (SEG-06). Se carga en diferido desde `AdminScreen`.
 */
export function RevisionArea() {
  return (
    <SiTienePermiso
      permiso="REVISAR_OBSERVACIONES"
      fallback={
        <main className="flex flex-col gap-4">
          <PageHeader titulo={TITULO} />
          <p className="text-sm text-primary/70">{SIN_PERMISO_DE_REVISION}</p>
        </main>
      }
    >
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <nav aria-label="Pestañas de revisión" className="flex gap-4 border-b border-border">
          <span className="flex items-center gap-1">
            <NavLink to="/admin/revision" end className={({ isActive }) => (isActive ? CLASE_PESTANA_ACTIVA : CLASE_PESTANA)}>
              Observaciones
            </NavLink>
            <Ayuda clave="revision.bandeja" />
          </span>
          <span className="flex items-center gap-1">
            <NavLink
              to="/admin/revision/rechazadas"
              className={({ isActive }) => (isActive ? CLASE_PESTANA_ACTIVA : CLASE_PESTANA)}
            >
              Rechazadas
            </NavLink>
            <Ayuda clave="revision.rechazadas" />
          </span>
        </nav>
        <Routes>
          <Route path="/" element={<ObservacionesScreen />} />
          <Route path="/rechazadas" element={<RechazadasScreen />} />
        </Routes>
      </main>
    </SiTienePermiso>
  )
}

export default RevisionArea
