import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { vi } from 'vitest'

import { ContextoSesion, type SesionRutaActiva } from '../../../src/areas/ruta/sesion/contextoSesion'

/** Monta una pantalla de `/ruta` con la sesión desbloqueada y un enrutador en memoria. */
export function montarEnRuta(
  pantalla: ReactNode,
  opciones: { ruta?: string; sesion?: Partial<SesionRutaActiva> } = {},
) {
  const sesion: SesionRutaActiva = {
    entrada: { tipo: 'al_dia' },
    alCerrarSesion: vi.fn(),
    alBloquearse: vi.fn(),
    reintentarEntrada: vi.fn(async () => undefined),
    ...opciones.sesion,
  }
  // Enrutador de datos (22b D10): Vender usa `useBlocker`, que no funciona con `MemoryRouter`.
  const router = createMemoryRouter(
    [{ path: '*', element: <ContextoSesion.Provider value={sesion}>{pantalla}</ContextoSesion.Provider> }],
    { initialEntries: [opciones.ruta ?? '/ruta'] },
  )
  const vista = render(<RouterProvider router={router} />)
  return { ...vista, sesion }
}
