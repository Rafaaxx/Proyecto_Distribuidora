import { Route, Routes } from 'react-router-dom'

import { ImportacionScreen } from './ImportacionScreen'

/**
 * Router del área de importación dentro de `/admin` (change 10, grupo 8, tarea 8.1). Se
 * carga en diferido desde `AdminScreen`, mismo criterio que `StockArea`/`ClientesArea`. Una
 * sola pantalla y una sola sección del menú, "Importación" (`IMPORTAR_DATOS`).
 */
export function ImportacionArea() {
  return (
    <Routes>
      <Route path="/" element={<ImportacionScreen />} />
    </Routes>
  )
}

export default ImportacionArea
