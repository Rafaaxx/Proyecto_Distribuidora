import { Route, Routes } from 'react-router-dom'

import { AyudaIndiceScreen } from '../../../ayuda/AyudaIndiceScreen'
import { AyudaTemaScreen } from '../../../ayuda/AyudaTemaScreen'

const BASE = '/ruta/ayuda'

/**
 * `/ruta/ayuda` (índice) y `/ruta/ayuda/:tema` (change 21, `design.md` D21; ADR-051). Son las
 * mismas pantallas de `/admin` con la base de ruta: sin datos del servidor, precacheadas, abren
 * sin conexión.
 */
export function AyudaRutaRoutes() {
  return (
    <Routes>
      <Route index element={<AyudaIndiceScreen base={BASE} />} />
      <Route path=":tema" element={<AyudaTemaScreen base={BASE} />} />
    </Routes>
  )
}

export default AyudaRutaRoutes
