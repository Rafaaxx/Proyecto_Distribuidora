import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  listarObservaciones,
  listarRechazos,
  obtenerRechazo,
  obtenerResumenDePendientes,
  resolverObservaciones,
  resolverRechazo,
  type ResolverObservacionesResultado,
  type ResolverRechazoDatos,
  type ResolverRechazoResultado,
} from './api'
import { clavesRevision, type FiltrosDeObservaciones, type FiltrosDeRechazos } from './claves'

/**
 * Lecturas y escrituras de la revisión (change 25). TanStack Query solo en `/admin` (`CLAUDE.md` §2). El
 * `Operation-Id` se genera una vez por envío y el reintento ante un error de RED reenvía el mismo valor (INV-06,
 * `useMutacionConOperationId`); un rechazo de dominio no se reintenta. Los comandos son `ONLINE`.
 */

/** Cada cuánto se vuelve a pedir el resumen del aviso (D5): 60 s y al volver a la pestaña. */
export const REFRESCO_DEL_AVISO_MS = 60_000

export function useObservaciones(filtros: FiltrosDeObservaciones = {}) {
  return useInfiniteQuery({
    queryKey: clavesRevision.observaciones(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarObservaciones(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useRechazos(filtros: FiltrosDeRechazos = {}) {
  return useInfiniteQuery({
    queryKey: clavesRevision.rechazos(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarRechazos(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

/** Lo que envió el teléfono, sin traducir. Sin id no pide nada. */
export function useRechazo(rechazoId: string | undefined) {
  return useQuery({
    queryKey: [...clavesRevision.raiz(), 'rechazo', rechazoId ?? ''] as const,
    queryFn: () => obtenerRechazo(rechazoId as string),
    enabled: rechazoId !== undefined,
  })
}

/**
 * El resumen del aviso (D5, CRE-09). `habilitado` es el permiso `REVISAR_OBSERVACIONES`: sin el permiso no se
 * pide nada (SEG-06). Se refresca solo cada 60 s y al volver a la pestaña.
 */
export function useResumenDePendientes(habilitado: boolean) {
  return useQuery({
    queryKey: clavesRevision.resumen(),
    queryFn: obtenerResumenDePendientes,
    enabled: habilitado,
    refetchInterval: REFRESCO_DEL_AVISO_MS,
    refetchOnWindowFocus: true,
  })
}

type VariablesResolverObservaciones = { observaciones: string[]; comentario: string; operationId?: string }
type VariablesResolverRechazo = ResolverRechazoDatos & { rechazoId: string; operationId?: string }

function useInvalidarTrasResolver() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesRevision.raiz() })
  }
}

export function useResolverObservaciones() {
  const invalidar = useInvalidarTrasResolver()
  return useMutacionConOperationId<VariablesResolverObservaciones, ResolverObservacionesResultado>(
    (variables, operationId) =>
      resolverObservaciones({ observaciones: variables.observaciones, comentario: variables.comentario }, operationId),
    invalidar,
  )
}

export function useResolverRechazo() {
  const invalidar = useInvalidarTrasResolver()
  return useMutacionConOperationId<VariablesResolverRechazo, ResolverRechazoResultado>(
    (variables, operationId) =>
      resolverRechazo(
        variables.rechazoId,
        { origen: variables.origen, comentario: variables.comentario, vinculo: variables.vinculo ?? null },
        operationId,
      ),
    invalidar,
  )
}
