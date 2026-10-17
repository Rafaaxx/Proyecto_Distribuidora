import { Route, Routes } from 'react-router-dom'

import { RolesScreen } from './RolesScreen'

/**
 * Router del área "Roles y permisos" dentro de `/admin` (change 17b, tarea 9.1). Se carga en
 * diferido desde `AdminScreen`. Una sola pantalla: `/admin/roles`.
 */
export function RolesArea() {
  return (
    <Routes>
      <Route path="/" element={<RolesScreen />} />
    </Routes>
  )
}

export default RolesArea
