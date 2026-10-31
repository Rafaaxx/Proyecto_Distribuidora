import { createContext, useContext } from 'react'

import type { ResultadoEntrada } from './entrada'

/** Lo que `SesionRuta` ofrece a las pantallas de `/ruta` una vez desbloqueada la sesión. */
export interface SesionRutaActiva {
  /** Qué pasó con los datos al entrar (el inicio lo usa para ofrecer abrir jornada o reintentar). */
  entrada: ResultadoEntrada
  /** Para el botón de cierre de sesión: vuelve a la pantalla de inicio de sesión. */
  alCerrarSesion: () => void
  /** Se agotaron los intentos del PIN (SEG-04): la derivación ya se borró; vuelve al login. */
  alBloquearse: () => void
  /** Vuelve a consultar la jornada y a pedir el bootstrap si hace falta. */
  reintentarEntrada: () => Promise<void>
}

export const ContextoSesion = createContext<SesionRutaActiva | null>(null)

export function useSesionRutaActiva(): SesionRutaActiva {
  const contexto = useContext(ContextoSesion)
  if (contexto === null) throw new Error('useSesionRutaActiva se usa dentro de <SesionRuta>')
  return contexto
}

