import { Route, Routes } from 'react-router-dom'

import { VentaDetalleScreen } from './VentaDetalleScreen'
import { VentaFormScreen } from './VentaFormScreen'
import { VentasListScreen } from './VentasListScreen'

/**
 * Router del área de ventas dentro de `/admin` (change 18a, tarea 12.2). Se carga en diferido
 * desde `AdminScreen`, mismo criterio que `CobranzasArea`. Una sola sección del menú, "Ventas"
 * (`VENDER` o `ANULAR_VENTA`, D19, D21); cada pantalla decide sus acciones con su permiso.
 * `/nueva` se declara antes que `/:ventaId`.
 */
export function VentasArea() {
  return (
    <Routes>
      <Route path="/" element={<VentasListScreen />} />
      <Route path="/nueva" element={<VentaFormScreen />} />
      <Route path="/:ventaId" element={<VentaDetalleScreen />} />
    </Routes>
  )
}

export default VentasArea
