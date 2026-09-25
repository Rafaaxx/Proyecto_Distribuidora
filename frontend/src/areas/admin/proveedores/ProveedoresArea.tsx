import { Route, Routes } from 'react-router-dom'

import { CostosCargaScreen } from './CostosCargaScreen'
import { CostosHistorialScreen } from './CostosHistorialScreen'
import { ProveedorFormScreen } from './ProveedorFormScreen'
import { ProveedoresListScreen } from './ProveedoresListScreen'

/**
 * Router del área de proveedores dentro de `/admin` (tarea 11.3, 11.4,
 * 11.5). Se carga en diferido desde `AdminScreen`, mismo criterio que
 * `CatalogoArea`: el bundle no se descarga hasta que alguien navega a
 * `/admin/proveedores`.
 */
export function ProveedoresArea() {
  return (
    <Routes>
      <Route path="/" element={<ProveedoresListScreen />} />
      <Route path="nuevo" element={<ProveedorFormScreen />} />
      <Route path=":proveedorId" element={<ProveedorFormScreen />} />
      <Route path=":proveedorId/costos" element={<CostosCargaScreen />} />
      <Route path="productos/:productoId/historial" element={<CostosHistorialScreen />} />
    </Routes>
  )
}

export default ProveedoresArea
