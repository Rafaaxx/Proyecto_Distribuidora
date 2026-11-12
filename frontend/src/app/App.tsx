import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { AppRoutes } from './AppRoutes'
import { PantallaDeError } from './PantallaDeError'

/**
 * Enrutador de datos con una sola ruta comodín que monta `AppRoutes` (change 22b, `design.md` D10):
 * las rutas descendientes no cambian, y la pantalla de venta puede bloquear la salida con
 * `useBlocker` (menú, enlaces, botón atrás).
 *
 * `errorElement` (change 27a, D19): un fallo de carga de pantalla diferida tras una actualización
 * muestra «Hay una versión nueva del sistema» con «Recargar», en lugar de la pantalla por defecto.
 */
const router = createBrowserRouter([{ path: '*', element: <AppRoutes />, errorElement: <PantallaDeError /> }])

export function App() {
  return <RouterProvider router={router} />
}

export default App
