import { Route, Routes } from 'react-router-dom'

import { CuentaCorrienteScreen } from '../cuentas-corrientes/CuentaCorrienteScreen'
import { SaldoInicialScreen } from '../cuentas-corrientes/SaldoInicialScreen'
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
      {/* Change 08 (D13): la cuenta corriente cuelga de la ficha, sin sección
          nueva en el menú. */}
      <Route path=":entidadId/cuenta-corriente" element={<CuentaCorrienteScreen cuentaTipo="PROVEEDOR" />} />
      <Route path=":entidadId/cuenta-corriente/saldo-inicial" element={<SaldoInicialScreen cuentaTipo="PROVEEDOR" />} />
      <Route path="productos/:productoId/historial" element={<CostosHistorialScreen />} />
    </Routes>
  )
}

export default ProveedoresArea
