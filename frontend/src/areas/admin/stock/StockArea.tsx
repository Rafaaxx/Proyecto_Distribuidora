import { Route, Routes } from 'react-router-dom'

import { KardexScreen } from './KardexScreen'
import { StockInicialScreen } from './StockInicialScreen'
import { StockPorUbicacionScreen } from './StockPorUbicacionScreen'
import { UbicacionesListScreen } from './UbicacionesListScreen'
import { UbicacionFormScreen } from './UbicacionFormScreen'

/**
 * Router del área de stock dentro de `/admin` (change 09, grupo 8, tareas 8.2 a
 * 8.4; `design.md` D15). Se carga en diferido desde `AdminScreen`, mismo criterio
 * que `ClientesArea`/`ProveedoresArea`. Una sola sección del menú, "Stock"
 * (`TRANSFERIR_STOCK`, D3); cada pantalla decide sus acciones con su permiso.
 *
 * `/ubicaciones/nueva` se declara antes que `/ubicaciones/:ubicacionId` (mismo
 * criterio que `/nuevo` en `ClientesArea`).
 */
export function StockArea() {
  return (
    <Routes>
      <Route path="/" element={<UbicacionesListScreen />} />
      <Route path="/ubicaciones/nueva" element={<UbicacionFormScreen />} />
      <Route path="/ubicaciones/:ubicacionId" element={<UbicacionFormScreen />} />
      <Route path="/ubicaciones/:ubicacionId/stock" element={<StockPorUbicacionScreen />} />
      <Route path="/ubicaciones/:ubicacionId/kardex/:productoId" element={<KardexScreen />} />
      <Route path="/ubicaciones/:ubicacionId/stock-inicial" element={<StockInicialScreen />} />
    </Routes>
  )
}

export default StockArea
