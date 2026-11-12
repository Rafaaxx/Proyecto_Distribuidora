import { Route, Routes } from 'react-router-dom'

import { PagoDetalleScreen } from './PagoDetalleScreen'
import { PagoFormScreen } from './PagoFormScreen'
import { PagosListScreen } from './PagosListScreen'

/**
 * Router del área de pagos a proveedores dentro de `/admin` (change 12, tarea 9.1). Se carga
 * en diferido desde `AdminScreen`, mismo criterio que `ComprasArea`. Una sola sección del
 * menú, "Pagos a proveedores" (`REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`, D7);
 * cada pantalla decide sus acciones con su permiso. `/nuevo` se declara antes que `/:pagoId`.
 */
export function PagosArea() {
  return (
    <Routes>
      <Route path="/" element={<PagosListScreen />} />
      <Route path="/nuevo" element={<PagoFormScreen />} />
      <Route path="/:pagoId" element={<PagoDetalleScreen />} />
    </Routes>
  )
}

export default PagosArea
