import { NavLink, Route, Routes, useLocation } from 'react-router-dom'

import { PaginaNoEncontrada } from '../../app/PaginaNoEncontrada'
import { useTituloDePagina } from '../../lib/useTituloDePagina'

import { AyudaRutaRoutes } from './ayuda/AyudaRutaRoutes'
import { ClienteFichaScreen } from './clientes/ClienteFichaScreen'
import { ClientesScreen } from './clientes/ClientesScreen'
import { CambiarPinScreen } from './cuenta/CambiarPinScreen'
import { MiContrasenaRutaScreen } from './cuenta/MiContrasenaRutaScreen'
import { MiCuentaScreen } from './cuenta/MiCuentaScreen'
import { InicioScreen } from './InicioScreen'
import { AbrirJornadaScreen } from './jornada/AbrirJornadaScreen'
import { ProductosScreen } from './productos/ProductosScreen'
import { IndicadorDeSincronizacion } from './sincronizacion/IndicadorDeSincronizacion'
import { SincronizacionScreen } from './sincronizacion/SincronizacionScreen'
import { StockScreen } from './stock/StockScreen'
import { AnularVentaScreen } from './ventas/AnularVentaScreen'
import { VenderScreen } from './ventas/VenderScreen'
import { VentaGuardadaScreen } from './ventas/VentaGuardadaScreen'
import { VentasDeHoyScreen } from './ventas/VentasDeHoyScreen'
import { CobranzaGuardadaScreen } from './cobranzas/CobranzaGuardadaScreen'
import { CobranzasDeHoyScreen } from './cobranzas/CobranzasDeHoyScreen'
import { CobrarScreen } from './cobranzas/CobrarScreen'

/**
 * Pantallas de `/ruta` con la sesión local ya desbloqueada (change 21, `design.md` D19): inicio,
 * jornada, consulta de clientes, productos y stock, cuenta y ayuda. Todo lo de consulta lee de la
 * base local. La venta de ruta (change 22a) va por `vender`, `ventas` y `ventas/:id`; la pantalla de venta pregunta antes de salir con líneas (22b D10, `useBlocker`).
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

/**
 * Título de la pestaña por pantalla, resuelto en un solo lugar: el primer prefijo que coincide
 * gana, así que los más específicos van antes. Sin coincidencia (la 404) devuelve `null` y la
 * pantalla hija fija el suyo.
 */
const TITULOS_DE_RUTA: readonly (readonly [prefijo: string, titulo: string])[] = [
  ['/ruta/jornada', 'Abrir jornada'],
  ['/ruta/clientes', 'Clientes'],
  ['/ruta/productos', 'Productos'],
  ['/ruta/stock', 'Stock'],
  ['/ruta/vender', 'Vender'],
  ['/ruta/ventas', 'Ventas de hoy'],
  ['/ruta/cobrar', 'Cobrar'],
  ['/ruta/cobranzas', 'Cobranzas de hoy'],
  ['/ruta/sincronizacion', 'Sincronización'],
  ['/ruta/cuenta', 'Mi cuenta'],
  ['/ruta/ayuda', 'Ayuda'],
]

function tituloDeRuta(pathname: string): string | null {
  const ruta = pathname.replace(/\/+$/, '')
  if (ruta === '/ruta') return 'Inicio'
  const hallado = TITULOS_DE_RUTA.find(([prefijo]) => ruta === prefijo || ruta.startsWith(`${prefijo}/`))
  return hallado ? hallado[1] : null
}

export function RutaLayout() {
  useTituloDePagina(tituloDeRuta(useLocation().pathname))

  return (
    <div className="flex min-h-dvh flex-col bg-surface-muted">
      <IndicadorDeSincronizacion />
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
          <Route path="ventas/:id/anular" element={<AnularVentaScreen />} />
          <Route path="cobrar" element={<CobrarScreen />} />
          <Route path="cobranzas" element={<CobranzasDeHoyScreen />} />
          <Route path="cobranzas/:id" element={<CobranzaGuardadaScreen />} />
          <Route path="sincronizacion" element={<SincronizacionScreen />} />
          <Route path="cuenta" element={<MiCuentaScreen />} />
          <Route path="cuenta/contrasena" element={<MiContrasenaRutaScreen />} />
          <Route path="cuenta/pin" element={<CambiarPinScreen />} />
          <Route path="ayuda/*" element={<AyudaRutaRoutes />} />
          <Route path="*" element={<PaginaNoEncontrada destino="/ruta" />} />
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
          >
            {item.texto}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export default RutaLayout
