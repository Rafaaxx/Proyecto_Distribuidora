import 'fake-indexeddb/auto'

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba } from '../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'

import { RutaLayout } from '../../../../src/areas/ruta/RutaLayout'
import { DefinirPinScreen, PedirPinScreen } from '../../../../src/areas/ruta/sesion/PantallasDePin'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

/**
 * Change 21, tareas 13.1, 14.x y 15.2: rutas de `/ruta` con la sesión desbloqueada y "(?)" del PIN
 * en las pantallas de definir y pedir el PIN (`ruta.pin`).
 */
describe('RutaLayout: rutas y menú de /ruta', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
  })

  function montar(ruta: string) {
    return montarEnRuta(
      <Routes>
        <Route path="/ruta/*" element={<RutaLayout />} />
      </Routes>,
      { ruta },
    )
  }

  it('el menú inferior navega entre las pantallas', async () => {
    montar('/ruta')
    const u = userEvent.setup()
    const menu = await screen.findByRole('navigation', { name: 'Menú de ruta' })
    expect(menu).toBeInTheDocument()

    await u.click(screen.getAllByRole('link', { name: 'Clientes' })[0] as HTMLElement)
    expect(await screen.findByRole('heading', { name: 'Clientes' })).toBeInTheDocument()

    await u.click(screen.getAllByRole('link', { name: 'Productos' })[0] as HTMLElement)
    expect(await screen.findByRole('heading', { name: 'Productos' })).toBeInTheDocument()

    await u.click(screen.getAllByRole('link', { name: 'Stock' })[0] as HTMLElement)
    expect(await screen.findByRole('heading', { name: 'Stock' })).toBeInTheDocument()

    await u.click(screen.getAllByRole('link', { name: 'Mi cuenta' })[0] as HTMLElement)
    expect(await screen.findByRole('heading', { name: 'Mi cuenta' })).toBeInTheDocument()
  })

  it('/ruta/ventas/:id/anular es una ruta de ruta (change 22d, tarea 10.1) y no vuelve al inicio', async () => {
    montar('/ruta/ventas/no-existe/anular')

    expect(await screen.findByText('No encontramos esa venta en este teléfono.')).toBeInTheDocument()
    expect(screen.queryByText(/Hola, /)).not.toBeInTheDocument()
  })

  it('/ruta/ayuda abre el índice de ayuda y una ruta desconocida muestra la 404 con vuelta a /ruta', async () => {
    const ayuda = montar('/ruta/ayuda')
    expect(await screen.findByRole('heading', { name: 'Ayuda' })).toBeInTheDocument()
    ayuda.unmount()

    montar('/ruta/lo-que-no-existe')
    expect(await screen.findByRole('heading', { name: 'Esta página no existe' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /volver al inicio/i })).toHaveAttribute('href', '/ruta')
    // El menú inferior sigue disponible: la 404 se ve dentro del área.
    expect(screen.getByRole('navigation', { name: 'Menú de ruta' })).toBeInTheDocument()
    expect(screen.queryByText(/Hola, Vendedor Uno/)).not.toBeInTheDocument()
  })

  it('el título de la pestaña sigue la pantalla activa de /ruta', async () => {
    const vender = montar('/ruta/vender')
    await screen.findByRole('heading', { name: 'Vender' })
    expect(document.title).toBe('Vender · Distribuidora')
    vender.unmount()

    const inicio = montar('/ruta')
    await screen.findByText(/Hola, Vendedor Uno/)
    expect(document.title).toBe('Inicio · Distribuidora')
    inicio.unmount()

    const cobrar = montar('/ruta/cobrar')
    await waitFor(() => expect(document.title).toBe('Cobrar · Distribuidora'))
    cobrar.unmount()
  })
})

describe('RutaLayout: rutas de la venta (change 22a, tarea 10.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
  })

  function montar(ruta: string) {
    return montarEnRuta(
      <Routes>
        <Route path="/ruta/*" element={<RutaLayout />} />
      </Routes>,
      { ruta },
    )
  }

  it('/ruta/vender abre la pantalla de venta, /ruta/ventas las ventas de hoy y /ruta/ventas/:id el detalle', async () => {
    const vender = montar('/ruta/vender')
    expect(await screen.findByRole('heading', { name: 'Vender' })).toBeInTheDocument()
    vender.unmount()

    const hoy = montar('/ruta/ventas')
    expect(await screen.findByRole('heading', { name: 'Ventas de hoy' })).toBeInTheDocument()
    hoy.unmount()

    montar('/ruta/ventas/no-existe')
    expect(await screen.findByText('No encontramos esa venta en este teléfono.')).toBeInTheDocument()
  })
})

describe('"(?)" del PIN en las pantallas de PIN (tarea 15.2)', () => {
  it('definir el PIN y pedir el PIN llevan la ayuda ruta.pin', () => {
    const definir = montarEnRuta(<DefinirPinScreen onDefinir={vi.fn(async () => null)} />)
    expect(screen.getByRole('button', { name: 'Ayuda: PIN de este teléfono' })).toBeInTheDocument()
    definir.unmount()

    montarEnRuta(<PedirPinScreen onDesbloquear={vi.fn(async () => null)} />)
    expect(screen.getByRole('button', { name: 'Ayuda: PIN de este teléfono' })).toBeInTheDocument()
  })
})
