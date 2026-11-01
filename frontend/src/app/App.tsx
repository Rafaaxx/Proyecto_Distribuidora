import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { AppRoutes } from './AppRoutes'

/**
 * Enrutador de datos con una sola ruta comodín que monta `AppRoutes` (change 22b, `design.md` D10):
 * las rutas descendientes no cambian, y la pantalla de venta puede bloquear la salida con
 * `useBlocker` (menú, enlaces, botón atrás).
 */
const router = createBrowserRouter([{ path: '*', element: <AppRoutes /> }])

export function App() {
  return <RouterProvider router={router} />
}

export default App
