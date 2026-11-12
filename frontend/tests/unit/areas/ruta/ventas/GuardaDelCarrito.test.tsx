import 'fake-indexeddb/auto'

import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ useRegisterSW: vi.fn() }))
vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: mocks.useRegisterSW }))

import { RutaLayout } from '../../../../../src/areas/ruta/RutaLayout'
import { ContextoSesion } from '../../../../../src/areas/ruta/sesion/contextoSesion'
import { ProveedorGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapParaVender } from '../../../utils/datosParaVender'

/**
 * Change 22b, tarea 11.2 (spec `sistema/aplicacion-instalable`, "Una versión nueva no se aplica con
 * un carrito abierto"; `design.md` D10; cita VTA-07, `02` §13.5): con líneas en el carrito, el menú,
 * "Cancelar" y el botón atrás del historial preguntan "¿Descartar la venta?"; `beforeunload` avisa
 * mientras hay líneas. Confirmar va a "Venta guardada" sin preguntar (cubierto por `VenderScreen`).
 */
function Ubicacion() {
  return <p data-testid="ubicacion">{useLocation().pathname}</p>
}

function montar(inicio: string[] = ['/ruta', '/ruta/vender']) {
  const router = createMemoryRouter(
    [
      {
        path: '/ruta/*',
        element: (
          <ContextoSesion.Provider
            value={{
              entrada: { tipo: 'al_dia' },
              alCerrarSesion: vi.fn(),
              alBloquearse: vi.fn(),
              reintentarEntrada: vi.fn(async () => undefined),
            }}
          >
            <ProveedorGuardaDelCarrito>
              <Ubicacion />
              <RutaLayout />
            </ProveedorGuardaDelCarrito>
          </ContextoSesion.Provider>
        ),
      },
    ],
    { initialEntries: inicio, initialIndex: inicio.length - 1 },
  )
  render(<RouterProvider router={router} />)
  return { router, u: userEvent.setup() }
}

async function cargarUnaLinea(u: ReturnType<typeof userEvent.setup>) {
  await u.click(await screen.findByRole('button', { name: /Almacén Uno/ }))
  await u.click(await screen.findByRole('button', { name: 'Agregar Gaseosa' }))
  const campo = await screen.findByLabelText('Unidades de Gaseosa')
  await u.clear(campo)
  await u.type(campo, '2')
}

function menu(): HTMLElement {
  return screen.getByRole('navigation', { name: 'Menú de ruta' })
}

describe('guarda completa del carrito con el enrutador de datos (tarea 11.2, D10, VTA-07)', () => {
  beforeEach(async () => {
    mocks.useRegisterSW.mockReturnValue({
      needRefresh: [false, vi.fn()],
      offlineReady: [false, vi.fn()],
      updateServiceWorker: vi.fn(),
    })
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('el botón atrás con líneas pregunta; "Seguir vendiendo" conserva el carrito y la pantalla', async () => {
    const { router, u } = montar()
    await cargarUnaLinea(u)

    await act(async () => {
      await router.navigate(-1)
    })

    expect(await screen.findByRole('dialog', { name: '¿Descartar la venta?' })).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Seguir vendiendo' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('ubicacion')).toHaveTextContent('/ruta/vender')
    expect(screen.getByLabelText('Unidades de Gaseosa')).toHaveValue(2)
  })

  it('el botón atrás con líneas y "Descartar" sale hacia atrás sin el carrito', async () => {
    const { router, u } = montar()
    await cargarUnaLinea(u)

    await act(async () => {
      await router.navigate(-1)
    })
    await u.click(await screen.findByRole('button', { name: 'Descartar' }))

    await waitFor(() => expect(screen.getByTestId('ubicacion').textContent).toBe('/ruta'))
  })

  it('el menú inferior con líneas pregunta; aceptar va a la pantalla elegida', async () => {
    const { u } = montar()
    await cargarUnaLinea(u)

    await u.click(within(menu()).getByRole('link', { name: 'Stock' }))
    await u.click(await screen.findByRole('button', { name: 'Descartar' }))

    await waitFor(() => expect(screen.getByTestId('ubicacion').textContent).toBe('/ruta/stock'))
  })

  it('un enlace del cuerpo ("Ver más" de una ayuda) con líneas pregunta antes de salir', async () => {
    const { u } = montar()
    await cargarUnaLinea(u)
    await u.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText(/paso 3 de 3/i)
    for (const boton of screen.getAllByRole('button', { name: /^Ayuda: / })) {
      await u.click(boton)
      const verMas = screen.queryByRole('link', { name: 'Ver más' })
      if (verMas === null) continue
      await u.click(verMas)
      break
    }

    expect(await screen.findByRole('dialog', { name: '¿Descartar la venta?' })).toBeInTheDocument()
    expect(screen.getByTestId('ubicacion')).toHaveTextContent('/ruta/vender')
  })

  it('"Cancelar" con líneas pregunta y, al aceptar, vuelve al inicio', async () => {
    const { u } = montar()
    await cargarUnaLinea(u)

    await u.click(screen.getByRole('button', { name: 'Cancelar' }))
    await u.click(await screen.findByRole('button', { name: 'Descartar' }))

    await waitFor(() => expect(screen.getByTestId('ubicacion').textContent).toBe('/ruta'))
  })

  it('sin líneas ni el menú ni el botón atrás preguntan', async () => {
    const { router, u } = montar()
    await screen.findByRole('button', { name: /Almacén Uno/ })

    await act(async () => {
      await router.navigate(-1)
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('ubicacion').textContent).toBe('/ruta'))
    await u.click(within(menu()).getByRole('link', { name: 'Productos' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('recargar o cerrar la pestaña con líneas pide el aviso del navegador; sin líneas no', async () => {
    const { u } = montar()
    const evento = () => {
      const e = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(e)
      return e
    }
    await screen.findByRole('button', { name: /Almacén Uno/ })
    expect(evento().defaultPrevented).toBe(false)

    await cargarUnaLinea(u)
    expect(evento().defaultPrevented).toBe(true)
  })
})
