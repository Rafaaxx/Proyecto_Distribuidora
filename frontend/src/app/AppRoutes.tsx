import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

// Carga diferida: el teléfono (área /ruta) no debe descargar el bundle de
// administración, y viceversa (docs/02-arquitectura.md §13.1).
const RutaScreen = lazy(() => import('../areas/ruta/RutaScreen'))
const AdminScreen = lazy(() => import('../areas/admin/AdminScreen'))

export function AppRoutes() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<Navigate to="/ruta" replace />} />
        <Route path="/ruta/*" element={<RutaScreen />} />
        <Route path="/admin/*" element={<AdminScreen />} />
      </Routes>
    </Suspense>
  )
}
