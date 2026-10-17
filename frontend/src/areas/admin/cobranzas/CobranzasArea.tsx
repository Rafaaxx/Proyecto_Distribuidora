import { Route, Routes } from 'react-router-dom'

import { CobranzaDetalleScreen } from './CobranzaDetalleScreen'
import { CobranzaFormScreen } from './CobranzaFormScreen'
import { CobranzasListScreen } from './CobranzasListScreen'

/**
 * Router del área de cobranzas dentro de `/admin` (change 17, tarea 14.1). Se carga en diferido
 * desde `AdminScreen`, mismo criterio que `PagosArea`. Una sola sección del menú, "Cobranzas"
 * (`REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`, D14); cada pantalla decide sus acciones con su
 * permiso. `/nuevo` se declara antes que `/:cobranzaId`.
 */
export function CobranzasArea() {
  return (
    <Routes>
      <Route path="/" element={<CobranzasListScreen />} />
      <Route path="/nuevo" element={<CobranzaFormScreen />} />
      <Route path="/:cobranzaId" element={<CobranzaDetalleScreen />} />
    </Routes>
  )
}

export default CobranzasArea
