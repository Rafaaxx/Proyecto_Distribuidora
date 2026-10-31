import { useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { Boton } from '../../components/ui/Button'
import { Dialogo } from '../../components/ui/Dialog'
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
import { useGuardaDelCarrito } from './ventas/contextoGuarda'
import { VenderScreen } from './ventas/VenderScreen'
import { VentaGuardadaScreen } from './ventas/VentaGuardadaScreen'
import { VentasDeHoyScreen } from './ventas/VentasDeHoyScreen'

/**
 * Pantallas de `/ruta` con la sesión local ya desbloqueada (change 21, `design.md` D19): inicio,
 * jornada, consulta de clientes, productos y stock, cuenta y ayuda. Todo lo de consulta lee de la
 * base local. La venta de ruta (change 22a) va por `vender`, `ventas` y `ventas/:id`; el menú
 * pregunta antes de salir de una venta con líneas (D12).
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
  const navegar = useNavigate()
  const { ocupado } = useGuardaDelCarrito()
  const [destinoPendiente, setDestinoPendiente] = useState<string | null>(null)

  // D12, VTA-07: con un carrito con líneas, salir por el menú pregunta antes de descartarlo.
  const alTocarMenu = (evento: React.MouseEvent, destino: string) => {
    if (!ocupado) return
    evento.preventDefault()
    setDestinoPendiente(destino)
  }
  const descartar = () => {
    const destino = destinoPendiente
    setDestinoPendiente(null)
    if (destino !== null) navegar(destino)
  }

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
          <Route path="vender" element={<VenderScreen />} />
          <Route path="ventas" element={<VentasDeHoyScreen />} />
          <Route path="ventas/:id" element={<VentaGuardadaScreen />} />
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
          <NavLink
            key={item.a}
            to={item.a}
            end={item.exacto}
            className={claseDeMenu}
            onClick={(evento) => alTocarMenu(evento, item.a)}
          >
            {item.texto}
          </NavLink>
        ))}
      </nav>
      <Dialogo abierto={destinoPendiente !== null} titulo="¿Descartar la venta?" onCerrar={() => setDestinoPendiente(null)}>
        <p className="mb-3 text-sm text-primary">Si salís ahora se pierde lo que cargaste. Todavía no se confirmó nada.</p>
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={() => setDestinoPendiente(null)}>
            Seguir vendiendo
          </Boton>
          <Boton variante="peligro" onClick={descartar}>
            Descartar
          </Boton>
        </div>
      </Dialogo>
    </div>
  )
}

export default RutaLayout
