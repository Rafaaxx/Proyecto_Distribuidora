import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'

import { PaginaInicial } from './PaginaInicial'
import { PaginaPrivacidad, PaginaTerminos } from './PaginaLegal'
import { PaginaNoEncontrada } from './PaginaNoEncontrada'

// Carga diferida: el teléfono (área /ruta) no debe descargar el bundle de
// administración, y viceversa (docs/02-arquitectura.md §13.1).
const RutaScreen = lazy(() => import('../areas/ruta/RutaScreen'))
const AdminScreen = lazy(() => import('../areas/admin/AdminScreen'))

export function AppRoutes() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<PaginaInicial />} />
        <Route path="/ruta/*" element={<RutaScreen />} />
        <Route path="/admin/*" element={<AdminScreen />} />
        <Route path="/privacidad" element={<PaginaPrivacidad />} />
        <Route path="/terminos" element={<PaginaTerminos />} />
        <Route path="*" element={<PaginaNoEncontrada destino="/" />} />
      </Routes>
    </Suspense>
  )
}
