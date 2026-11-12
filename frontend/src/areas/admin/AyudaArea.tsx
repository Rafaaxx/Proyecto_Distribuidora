import { Route, Routes } from 'react-router-dom'

import { AyudaIndiceScreen } from '../../ayuda/AyudaIndiceScreen'
import { AyudaTemaScreen } from '../../ayuda/AyudaTemaScreen'

/** `/admin/ayuda` (índice) y `/admin/ayuda/:tema` (change 16b, ADR-051, D5 = A). */
export function AyudaArea() {
  return (
    <Routes>
      <Route index element={<AyudaIndiceScreen />} />
      <Route path=":tema" element={<AyudaTemaScreen />} />
    </Routes>
  )
}

export default AyudaArea
