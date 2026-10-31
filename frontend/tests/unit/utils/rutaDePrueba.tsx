import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
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
  const vista = render(
    <MemoryRouter initialEntries={[opciones.ruta ?? '/ruta']}>
      <ContextoSesion.Provider value={sesion}>{pantalla}</ContextoSesion.Provider>
    </MemoryRouter>,
  )
  return { ...vista, sesion }
}
