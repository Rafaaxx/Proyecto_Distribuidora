import { useQuery } from '@tanstack/react-query'

import { obtenerConsistencia } from './api'
import { clavesSistema } from './claves'

/** Cada cuánto se vuelve a pedir el resultado (D5): la verificación corre una vez por noche, no hace falta más. */
export const REFRESCO_DE_LA_CONSISTENCIA_MS = 10 * 60_000

/**
 * El último resultado de la verificación de consistencia (change 28, D5). `habilitado` es el permiso
 * `VER_CONSISTENCIA`: sin él no se pide nada (SEG-06). TanStack Query solo en `/admin` (`CLAUDE.md` §2).
 */
export function useConsistencia(habilitado: boolean) {
  return useQuery({
    queryKey: clavesSistema.consistencia(),
    queryFn: obtenerConsistencia,
    enabled: habilitado,
    refetchInterval: REFRESCO_DE_LA_CONSISTENCIA_MS,
    refetchOnWindowFocus: true,
  })
}
