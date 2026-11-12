import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import { guardarArchivo } from '../../lib/descarga'
import { descargarPlantilla, importarArchivo, listarImportaciones, type ImportacionResultado } from './api'
import { clavesImportacion } from './claves'

/**
 * Lecturas y escrituras de importación (change 10, grupo 8, tareas 8.1 y 8.2). TanStack
 * Query solo en `/admin` (`CLAUDE.md` §2).
 *
 * El `Operation-Id` del envío se toma de `variables.operationId` (que conserva la pantalla
 * para reintentar tras un corte de red) o se genera una vez en `onMutate`; `mutationFn` lo
 * lee en cada intento, así el reintento automático reenvía exactamente el mismo valor
 * (INV-06). `retry` usa `debeReintentar`: solo un error de RED, nunca un rechazo de dominio
 * ya resuelto. Es `ONLINE` puro: agotados los reintentos no se encola nada.
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

export function useHistorialDeImportaciones() {
  return useInfiniteQuery({
    queryKey: clavesImportacion.historial(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarImportaciones(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export interface VariablesDeImportacion {
  tipo: string
  archivo: File
  operationId?: string
}

export function useImportarArchivo() {
  const queryClient = useQueryClient()
  const operationIdRef = useRef<string | null>(null)
  return useMutation<ImportacionResultado, Error, VariablesDeImportacion>({
    retry: debeReintentar,
    retryDelay: 0,
    onMutate: (variables) => {
      operationIdRef.current = variables.operationId ?? generarOperationId()
    },
    mutationFn: (variables) =>
      importarArchivo(variables.tipo, variables.archivo, operationIdRef.current ?? generarOperationId()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clavesImportacion.raiz() })
    },
  })
}

/** Descarga la plantilla CSV del tipo y la guarda como `plantilla-{tipo}.csv`. */
export function useDescargarPlantilla() {
  return useMutation<void, Error, string>({
    mutationFn: async (tipo) => {
      const archivo = await descargarPlantilla(tipo)
      guardarArchivo(archivo, `plantilla-${tipo.toLowerCase()}.csv`)
    },
  })
}
