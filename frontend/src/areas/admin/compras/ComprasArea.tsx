import { Route, Routes } from 'react-router-dom'

import { CompraDetalleScreen } from './CompraDetalleScreen'
import { CompraFormScreen } from './CompraFormScreen'
import { ComprasListScreen } from './ComprasListScreen'

/**
 * Router del área de compras dentro de `/admin` (change 11, tarea 12.1). Se carga en
 * diferido desde `AdminScreen`, mismo criterio que `StockArea`. Una sola sección del menú,
 * "Compras" (`REGISTRAR_COMPRA` o `ANULAR_COMPRA`, D14); cada pantalla decide sus
 * acciones con su permiso. `/nueva` se declara antes que `/:compraId`.
 */
export function ComprasArea() {
  return (
    <Routes>
      <Route path="/" element={<ComprasListScreen />} />
      <Route path="/nueva" element={<CompraFormScreen />} />
      <Route path="/:compraId" element={<CompraDetalleScreen />} />
    </Routes>
  )
}

export default ComprasArea
