import { Route, Routes } from 'react-router-dom'

import { PageHeader } from '../../../components/ui/PageHeader'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { UsuarioAltaScreen } from './UsuarioAltaScreen'
import { UsuarioFichaScreen } from './UsuarioFichaScreen'
import { UsuariosListScreen } from './UsuariosListScreen'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Usuarios" />
      <p className="text-sm text-primary/70">No tenés permiso para administrar usuarios, roles y permisos.</p>
    </main>
  )
}

/**
 * Router del área "Usuarios" dentro de `/admin` (change 20b, tarea 10.1; D16): listado, alta y
 * ficha. Se carga en diferido desde `AdminScreen`. Todo con `ADMIN_USUARIOS` (ADR-027); el
 * servidor valida igual (SEG-06).
 */
export function UsuariosArea() {
  return (
    <SiTienePermiso permiso="ADMIN_USUARIOS" fallback={<SinPermiso />}>
      <Routes>
        <Route path="/" element={<UsuariosListScreen />} />
        <Route path="nuevo" element={<UsuarioAltaScreen />} />
        <Route path=":usuarioId" element={<UsuarioFichaScreen />} />
      </Routes>
    </SiTienePermiso>
  )
}

export default UsuariosArea
