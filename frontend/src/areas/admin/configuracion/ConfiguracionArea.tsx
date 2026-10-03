import { Navigate, Route, Routes } from 'react-router-dom'

import { ConfiguracionFiscalScreen } from './ConfiguracionFiscalScreen'

/**
 * Router del área de configuración dentro de `/admin` (change 11b, tarea 7.4). Se carga en
 * diferido desde `AdminScreen`. Una sola pantalla por ahora, `/admin/configuracion/fiscal`; la
 * ruta índice lleva a ella.
 */
export function ConfiguracionArea() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="fiscal" replace />} />
      <Route path="fiscal" element={<ConfiguracionFiscalScreen />} />
    </Routes>
  )
}

export default ConfiguracionArea
