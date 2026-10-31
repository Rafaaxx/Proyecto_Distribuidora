import 'fake-indexeddb/auto'

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ useRegisterSW: vi.fn() }))
vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: mocks.useRegisterSW }))

import { AvisoDeVersion } from '../../../../../src/areas/ruta/pwa/AvisoDeVersion'
import { RutaLayout } from '../../../../../src/areas/ruta/RutaLayout'
import { useGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/contextoGuarda'
import { ProveedorGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { ContextoSesion } from '../../../../../src/areas/ruta/sesion/contextoSesion'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapDePrueba } from '../../../utils/bootstrapDePrueba'

/**
 * Change 22a, tarea 13.1 (spec `sistema/aplicacion-instalable`, "Una versión nueva no se aplica con
 * un carrito abierto"; `design.md` D12; cita `02` §13.5, VTA-07): con un carrito con líneas el
 * aviso de versión nueva no ofrece "Actualizar"; al confirmar o descartar vuelve; salir de la
 * venta con líneas pregunta "¿Descartar la venta?".
 */
function registro(necesitaActualizar: boolean, actualizar = vi.fn(async () => undefined)) {
  mocks.useRegisterSW.mockReturnValue({
    needRefresh: [necesitaActualizar, vi.fn()],
    offlineReady: [false, vi.fn()],
    updateServiceWorker: actualizar,
  })
  return actualizar
}

function Marcador() {
  const { marcar } = useGuardaDelCarrito()
  return (
    <>
      <button type="button" onClick={() => marcar(true)}>
        abrir carrito
      </button>
      <button type="button" onClick={() => marcar(false)}>
        cerrar carrito
      </button>
    </>
  )
}

describe('AvisoDeVersion con la guarda del carrito (tarea 13.1, D12)', () => {
  beforeEach(() => mocks.useRegisterSW.mockReset())

  it('con un carrito abierto dice que se instala al terminar la venta y no ofrece "Actualizar"', async () => {
    const actualizar = registro(true)
    render(
      <ProveedorGuardaDelCarrito>
        <Marcador />
        <AvisoDeVersion />
      </ProveedorGuardaDelCarrito>,
    )
    const u = userEvent.setup()

    expect(screen.getByRole('button', { name: 'Actualizar' })).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'abrir carrito' }))

    expect(screen.getByRole('status')).toHaveTextContent('Hay una versión nueva: se instala al terminar la venta')
    expect(screen.queryByRole('button', { name: 'Actualizar' })).not.toBeInTheDocument()
    expect(actualizar).not.toHaveBeenCalled()
  })

  it('al confirmar o descartar el carrito vuelve "Actualizar" (solo recarga al tocarlo)', async () => {
    const actualizar = registro(true)
    render(
      <ProveedorGuardaDelCarrito>
        <Marcador />
        <AvisoDeVersion />
      </ProveedorGuardaDelCarrito>,
    )
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: 'abrir carrito' }))
    await u.click(screen.getByRole('button', { name: 'cerrar carrito' }))

    expect(screen.getByRole('status')).toHaveTextContent('Hay una versión nueva')
    await u.click(screen.getByRole('button', { name: 'Actualizar' }))
    expect(actualizar).toHaveBeenCalledWith(true)
  })

  it('con el carrito abierto y sin versión nueva no muestra nada', async () => {
    registro(false)
    render(
      <ProveedorGuardaDelCarrito>
        <Marcador />
        <AvisoDeVersion />
      </ProveedorGuardaDelCarrito>,
    )
    await userEvent.setup().click(screen.getByRole('button', { name: 'abrir carrito' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

function menu(): HTMLElement {
  return screen.getByRole('navigation', { name: 'Menú de ruta' })
}

function Ubicacion() {
  return <p data-testid="ubicacion">{useLocation().pathname}</p>
}

describe('salir de la venta con líneas (tarea 13.1, VTA-07)', () => {
  beforeEach(async () => {
    mocks.useRegisterSW.mockReset()
    registro(false)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
  })

  function montar() {
    render(
      <MemoryRouter initialEntries={['/ruta']}>
        <ContextoSesion.Provider
          value={{
            entrada: { tipo: 'al_dia' },
            alCerrarSesion: vi.fn(),
            alBloquearse: vi.fn(),
            reintentarEntrada: vi.fn(async () => undefined),
          }}
        >
          <ProveedorGuardaDelCarrito>
            <Marcador />
            <Ubicacion />
            <Routes>
              <Route path="/ruta/*" element={<RutaLayout />} />
            </Routes>
          </ProveedorGuardaDelCarrito>
        </ContextoSesion.Provider>
      </MemoryRouter>,
    )
  }

  it('pregunta "¿Descartar la venta?" y, si no acepta, no sale y el carrito sigue igual', async () => {
    montar()
    const u = userEvent.setup()
    await screen.findByRole('navigation', { name: 'Menú de ruta' })
    await u.click(screen.getByRole('button', { name: 'abrir carrito' }))

    await u.click(within(menu()).getByRole('link', { name: 'Clientes' }))
    expect(await screen.findByRole('dialog', { name: '¿Descartar la venta?' })).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Seguir vendiendo' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('ubicacion')).toHaveTextContent('/ruta')
    expect(screen.getByTestId('ubicacion')).not.toHaveTextContent('/ruta/clientes')
  })

  it('si acepta, sale a la pantalla elegida', async () => {
    montar()
    const u = userEvent.setup()
    await screen.findByRole('navigation', { name: 'Menú de ruta' })
    await u.click(screen.getByRole('button', { name: 'abrir carrito' }))

    await u.click(within(menu()).getByRole('link', { name: 'Stock' }))
    await u.click(await screen.findByRole('button', { name: 'Descartar' }))

    await waitFor(() => expect(screen.getByTestId('ubicacion')).toHaveTextContent('/ruta/stock'))
  })

  it('sin carrito abierto el menú navega sin preguntar', async () => {
    montar()
    const u = userEvent.setup()
    await screen.findByRole('navigation', { name: 'Menú de ruta' })

    await u.click(within(menu()).getByRole('link', { name: 'Productos' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('ubicacion')).toHaveTextContent('/ruta/productos'))
  })
})
