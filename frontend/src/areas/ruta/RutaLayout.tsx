import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { AyudaRutaRoutes } from './ayuda/AyudaRutaRoutes'
import { ClienteFichaScreen } from './clientes/ClienteFichaScreen'
import { ClientesScreen } from './clientes/ClientesScreen'
import { CambiarPinScreen } from './cuenta/CambiarPinScreen'
import { MiContrasenaRutaScreen } from './cuenta/MiContrasenaRutaScreen'
import { MiCuentaScreen } from './cuenta/MiCuentaScreen'
import { InicioScreen } from './InicioScreen'
import { AbrirJornadaScreen } from './jornada/AbrirJornadaScreen'
import { ProductosScreen } from './productos/ProductosScreen'
import { StockScreen } from './stock/StockScreen'

/**
 * Pantallas de `/ruta` con la sesión local ya desbloqueada (change 21, `design.md` D19): inicio,
 * jornada, consulta de clientes, productos y stock, cuenta y ayuda. Todo lo de consulta lee de la
 * base local. La venta sigue en `/admin` hasta el change 22a.
 */
const MENU = [
  { a: '/ruta', texto: 'Inicio', exacto: true },
  { a: '/ruta/clientes', texto: 'Clientes', exacto: false },
  { a: '/ruta/productos', texto: 'Productos', exacto: false },
  { a: '/ruta/stock', texto: 'Stock', exacto: false },
  { a: '/ruta/cuenta', texto: 'Mi cuenta', exacto: false },
] as const

function claseDeMenu({ isActive }: { isActive: boolean }): string {
  return [
    'flex flex-1 items-center justify-center px-1 py-3 text-xs font-medium',
    isActive ? 'bg-primary text-primary-foreground' : 'text-primary hover:bg-surface-muted',
  ].join(' ')
}

export function RutaLayout() {
  return (
    <div className="flex min-h-dvh flex-col bg-surface-muted">
      <main className="flex-1 p-4 pb-20">
        <Routes>
          <Route index element={<InicioScreen />} />
          <Route path="jornada/abrir" element={<AbrirJornadaScreen />} />
          <Route path="clientes" element={<ClientesScreen />} />
          <Route path="clientes/:id" element={<ClienteFichaScreen />} />
          <Route path="productos" element={<ProductosScreen />} />
          <Route path="stock" element={<StockScreen />} />
          <Route path="cuenta" element={<MiCuentaScreen />} />
          <Route path="cuenta/contrasena" element={<MiContrasenaRutaScreen />} />
          <Route path="cuenta/pin" element={<CambiarPinScreen />} />
          <Route path="ayuda/*" element={<AyudaRutaRoutes />} />
          <Route path="*" element={<Navigate to="/ruta" replace />} />
        </Routes>
      </main>
      <nav
        aria-label="Menú de ruta"
        className="fixed inset-x-0 bottom-0 z-10 flex border-t border-border bg-surface"
      >
        {MENU.map((item) => (
          <NavLink key={item.a} to={item.a} end={item.exacto} className={claseDeMenu}>
            {item.texto}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export default RutaLayout
