import { Route, Routes } from 'react-router-dom'

import { CuentaCorrienteScreen } from '../cuentas-corrientes/CuentaCorrienteScreen'
import { SaldoInicialScreen } from '../cuentas-corrientes/SaldoInicialScreen'
import { ClienteCreditoScreen } from './ClienteCreditoScreen'
import { ClienteFormScreen } from './ClienteFormScreen'
import { ClientesListScreen } from './ClientesListScreen'
import { ConsumidorFinalScreen } from './ConsumidorFinalScreen'

/**
 * Router del área de clientes dentro de `/admin` (change 07, grupo 5,
 * tareas 5.2 a 5.5). Se carga en diferido desde `AdminScreen`, mismo
 * criterio que `ProveedoresArea`/`CatalogoArea`.
 *
 * Las cuatro escrituras del módulo (`CLIENTE_CREAR`, `CLIENTE_MODIFICAR`,
 * `CLIENTE_CREDITO_MODIFICAR`, `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`) tienen
 * ahora su ruta HTTP dedicada (`design.md` D9, enmienda 2026-09-29), así
 * que la ficha de alta/edición, la pantalla de crédito y la de habilitación
 * del consumidor final ya pueden implementarse de punta a punta.
 *
 * `/nuevo` y `/consumidor-final` se declaran antes que `/:clienteId` para
 * que React Router no intente resolverlos como un id (mismo criterio que
 * `/proveedores/opciones` en el backend, aunque acá el ranking de rutas de
 * React Router ya resuelve la ruta estática primero por especificidad).
 */
export function ClientesArea() {
  return (
    <Routes>
      <Route path="/" element={<ClientesListScreen />} />
      <Route path="/nuevo" element={<ClienteFormScreen />} />
      <Route path="/consumidor-final" element={<ConsumidorFinalScreen />} />
      <Route path="/:clienteId" element={<ClienteFormScreen />} />
      <Route path="/:clienteId/credito" element={<ClienteCreditoScreen />} />
      {/* Change 08 (D13): la cuenta corriente cuelga de la ficha, sin sección
          nueva en el menú. */}
      <Route path="/:entidadId/cuenta-corriente" element={<CuentaCorrienteScreen cuentaTipo="CLIENTE" />} />
      <Route path="/:entidadId/cuenta-corriente/saldo-inicial" element={<SaldoInicialScreen cuentaTipo="CLIENTE" />} />
    </Routes>
  )
}

export default ClientesArea
