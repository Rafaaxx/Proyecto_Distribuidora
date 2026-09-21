import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'

import { LoginScreen } from './auth/LoginScreen'
import { DispositivosScreen } from './dispositivos/DispositivosScreen'

/**
 * `docs/02-arquitectura.md` §13.1: `/admin` usa TanStack Query contra la
 * API (a diferencia de `/ruta`, que solo lee de Dexie); el `QueryClient` se
 * crea acá para que solo exista mientras el área de administración está
 * montada (carga diferida, `AppRoutes.tsx`).
 *
 * Sin sesión restaurada todavía (ese flujo no lo pide ningún escenario de
 * este change): la raíz de `/admin` redirige siempre a `login`. Cambia
 * cuando exista una pantalla que dependa de sesión persistida entre
 * recargas.
 */
const queryClient = new QueryClient()

export function AdminScreen() {
  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/" element={<Navigate to="login" replace />} />
        <Route path="login" element={<LoginScreen />} />
        <Route path="dispositivos" element={<DispositivosScreen />} />
      </Routes>
    </QueryClientProvider>
  )
}

export default AdminScreen
