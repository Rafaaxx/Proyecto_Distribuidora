import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../src/sync/appVersion', () => ({ APP_VERSION: '1.2.0' }))

import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { RutaLayout } from '../../../../src/areas/ruta/RutaLayout'
import { SincronizacionScreen } from '../../../../src/areas/ruta/sincronizacion/SincronizacionScreen'
import { VentaGuardadaScreen } from '../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { VentasDeHoyScreen } from '../../../../src/areas/ruta/ventas/VentasDeHoyScreen'
import { claveDeAyudaDeEnvio } from '../../../../src/areas/ruta/ventas/presentacionDeVentas'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { CLAVE_VERSION_MINIMA } from '../../../../src/sync/versionMinima'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarVenta } from '../../utils/sembrarVenta'

/**
 * Change 22b, tarea 12.1 (spec `sistema/ayuda-contextual`, «La sincronización del área de ruta
 * explica sus estados»; `design.md` D13; ADR-051): dónde aparece cada «(?)» nuevo de `/ruta`.
 */
async function marcarEstado(sufijo: string, estado: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA') {
  await baseLocal.ventas.update(`venta-${sufijo}`, { estado_envio: estado })
}

describe('ayudas de la sincronización en las pantallas de /ruta (tarea 12.1)', () => {
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('claveDeAyudaDeEnvio: cada estado con problema o pendiente tiene su ayuda; la enviada, ninguna', () => {
    expect(claveDeAyudaDeEnvio('PENDIENTE')).toBe('ruta.ventaSinEnviar')
    expect(claveDeAyudaDeEnvio('CON_OBSERVACIONES')).toBe('ruta.ventaConObservaciones')
    expect(claveDeAyudaDeEnvio('RECHAZADA')).toBe('ruta.ventaRechazada')
    expect(claveDeAyudaDeEnvio('ACEPTADA')).toBeNull()
  })

  it('la cabecera de /ruta tiene la ayuda «Sincronizar»', async () => {
    montarEnRuta(
      <Routes>
        <Route path="/ruta/*" element={<RutaLayout />} />
      </Routes>,
      { ruta: '/ruta/clientes' },
    )
    const cabecera = await screen.findByRole('banner')
    expect(within(cabecera).getByRole('button', { name: 'Ayuda: Sincronizar' })).toBeInTheDocument()
  })

  it('el inicio tiene la ayuda «Sincronizar» junto al botón', async () => {
    montarEnRuta(<InicioScreen />)
    await screen.findByRole('button', { name: 'Sincronizar' })
    expect(screen.getByRole('button', { name: 'Ayuda: Sincronizar' })).toBeInTheDocument()
  })

  it('«Sincronización» explica Sincronizar, Con observaciones y Rechazadas', async () => {
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    await marcarEstado('b', 'CON_OBSERVACIONES')
    await sembrarVenta('c', { cajas: 1, unidades: 0 })
    await marcarEstado('c', 'RECHAZADA')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await screen.findAllByRole('listitem')
    expect(screen.getByRole('button', { name: 'Ayuda: Sincronizar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Con observaciones' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Rechazada' })).toBeInTheDocument()
  })

  it('«Ventas de hoy» explica solo los estados que tiene en la lista', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    await marcarEstado('b', 'RECHAZADA')
    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    await screen.findAllByRole('listitem')
    expect(screen.getByRole('button', { name: 'Ayuda: Sin enviar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Rechazada' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ayuda: Con observaciones' })).not.toBeInTheDocument()
  })

  it('el detalle de la venta muestra la ayuda de su estado (rechazada, no «Sin enviar») y ninguna si fue enviada', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await marcarEstado('a', 'RECHAZADA')
    const vista = montarEnRuta(
      <Routes>
        <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
      </Routes>,
      { ruta: '/ruta/ventas/venta-a' },
    )
    await screen.findByRole('heading', { name: /Venta/ })
    expect(screen.getByRole('button', { name: 'Ayuda: Rechazada' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ayuda: Sin enviar' })).not.toBeInTheDocument()
    vista.unmount()

    await marcarEstado('a', 'ACEPTADA')
    montarEnRuta(
      <Routes>
        <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
      </Routes>,
      { ruta: '/ruta/ventas/venta-a' },
    )
    await screen.findByRole('heading', { name: /Venta/ })
    expect(screen.queryByRole('button', { name: 'Ayuda: Rechazada' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ayuda: Sin enviar' })).not.toBeInTheDocument()
  })

  it('el aviso de versión mínima del inicio tiene la ayuda «Versión desactualizada»', async () => {
    await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor: '1.3.0' })
    montarEnRuta(<InicioScreen />)

    await screen.findByText('Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación')
    expect(screen.getByRole('button', { name: 'Ayuda: Versión desactualizada' })).toBeInTheDocument()
  })

  it('con la versión al día no hay ayuda de versión', async () => {
    await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor: '1.2.0' })
    montarEnRuta(<InicioScreen />)

    await screen.findByRole('link', { name: 'Vender' })
    expect(screen.queryByRole('button', { name: 'Ayuda: Versión desactualizada' })).not.toBeInTheDocument()
  })
})
