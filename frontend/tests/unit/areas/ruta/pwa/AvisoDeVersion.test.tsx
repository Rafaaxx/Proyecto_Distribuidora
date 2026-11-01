import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ useRegisterSW: vi.fn() }))
vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: mocks.useRegisterSW }))

import { AvisoDeVersion } from '../../../../../src/areas/ruta/pwa/AvisoDeVersion'
import { useGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/contextoGuarda'
import { ProveedorGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/guardaDelCarrito'

/**
 * Change 22a, tarea 13.1 (spec `sistema/aplicacion-instalable`, "Una versión nueva no se aplica con
 * un carrito abierto"; `design.md` D12; cita `02` §13.5, VTA-07): con un carrito con líneas el
 * aviso de versión nueva no ofrece "Actualizar"; al confirmar o descartar vuelve. Salir de la venta con
 * líneas ("¿Descartar la venta?") se prueba en `ventas/GuardaDelCarrito.test.tsx` (22b D10).
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
