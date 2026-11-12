import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ useRegisterSW: vi.fn() }))
vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: mocks.useRegisterSW }))

import { AvisoDeVersion } from '../../../src/areas/ruta/pwa/AvisoDeVersion'

/**
 * Change 21, tarea 11.3 (spec `sistema/aplicacion-instalable`, "Una versión nueva se aplica con
 * aviso"; `design.md` D17; `02` §13.5): el aviso aparece cuando hay una versión nueva y la pantalla
 * no se recarga hasta que el usuario toca "Actualizar".
 */
function registro(necesitaActualizar: boolean, actualizar = vi.fn(async () => undefined)) {
  mocks.useRegisterSW.mockReturnValue({
    needRefresh: [necesitaActualizar, vi.fn()],
    offlineReady: [false, vi.fn()],
    updateServiceWorker: actualizar,
  })
  return actualizar
}

describe('AvisoDeVersion (tarea 11.3)', () => {
  beforeEach(() => mocks.useRegisterSW.mockReset())

  it('sin versión nueva no muestra nada', () => {
    registro(false)
    render(<AvisoDeVersion />)
    expect(screen.queryByText(/hay una versión nueva/i)).not.toBeInTheDocument()
  })

  it('con versión nueva muestra el aviso y no recarga hasta tocar "Actualizar"', async () => {
    const actualizar = registro(true)
    render(<AvisoDeVersion />)

    expect(screen.getByRole('status')).toHaveTextContent('Hay una versión nueva')
    expect(actualizar).not.toHaveBeenCalled()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Actualizar' }))
    expect(actualizar).toHaveBeenCalledTimes(1)
    expect(actualizar).toHaveBeenCalledWith(true)
  })

  it('registra el service worker en modo de aviso (sin recarga automática)', () => {
    registro(false)
    render(<AvisoDeVersion />)
    const opciones = mocks.useRegisterSW.mock.calls[0]?.[0] as { immediate?: boolean } | undefined
    expect(opciones?.immediate).toBe(true)
  })
})
