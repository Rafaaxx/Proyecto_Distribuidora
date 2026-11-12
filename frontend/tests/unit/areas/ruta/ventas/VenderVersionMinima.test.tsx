import 'fake-indexeddb/auto'

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../../src/sync/appVersion', () => ({ APP_VERSION: '1.2.0' }))

import { ClienteFichaScreen } from '../../../../../src/areas/ruta/clientes/ClienteFichaScreen'
import { InicioScreen } from '../../../../../src/areas/ruta/InicioScreen'
import { ProveedorGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { VenderScreen } from '../../../../../src/areas/ruta/ventas/VenderScreen'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { CLAVE_VERSION_MINIMA } from '../../../../../src/sync/versionMinima'
import { ID } from '../../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../../utils/datosParaVender'
import { montarEnRuta } from '../../../utils/rutaDePrueba'

/**
 * Change 22b, tarea 9.2 (spec `ruta/area-de-ruta`, «Vender se deshabilita por debajo de la versión
 * mínima»; `design.md` D7; cita `02` §6.6, VTA-07): la aplicación está en 1.2.0.
 */
const AVISO = 'Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación'

async function fijarMinima(valor: string | null) {
  if (valor === null) await baseLocal.meta.delete(CLAVE_VERSION_MINIMA)
  else await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor })
}

describe('Vender por debajo de la versión mínima (tarea 9.2)', () => {
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('el inicio deshabilita «Vender» con el aviso y deja «Ventas de hoy» y «Sincronizar»', async () => {
    await fijarMinima('1.3.0')
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(screen.queryByRole('link', { name: 'Vender' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ventas de hoy' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })

  it('con la versión al día (o sin mínima conocida) «Vender» sigue disponible', async () => {
    await fijarMinima('1.2.0')
    montarEnRuta(<InicioScreen />)
    expect(await screen.findByRole('link', { name: 'Vender' })).toBeInTheDocument()
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument()
  })

  it('la ficha del cliente deshabilita «Vender» con el mismo aviso', async () => {
    await fijarMinima('1.3.0')
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${ID(101)}` },
    )

    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
  })

  it('con el carrito abierto, si llega el aviso «Confirmar venta» no confirma, el carrito sigue y se muestra el aviso', async () => {
    montarEnRuta(
      <ProveedorGuardaDelCarrito>
        <Routes>
          <Route path="/ruta/vender" element={<VenderScreen />} />
        </Routes>
      </ProveedorGuardaDelCarrito>,
      { ruta: '/ruta/vender' },
    )
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: /Almacén Uno/ }))
    await u.click(await screen.findByRole('button', { name: 'Agregar Gaseosa' }))
    const cajas = await screen.findByLabelText('Cajas de Gaseosa')
    await u.clear(cajas)
    await u.type(cajas, '1')
    await u.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText(/paso 3 de 3/i)

    // El aviso llega con el carrito abierto.
    await fijarMinima('1.3.0')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(0)
    expect(await baseLocal.cola.count()).toBe(0)
    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeInTheDocument()

    // Al actualizarse la mínima (por ejemplo a la versión propia) se puede confirmar el mismo carrito.
    await fijarMinima('1.2.0')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await vi.waitFor(async () => expect(await baseLocal.ventas.count()).toBe(1))
  })
})
