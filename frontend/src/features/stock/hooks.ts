import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import {
  crearUbicacion,
  modificarUbicacion,
  obtenerCostoPromedio,
  obtenerKardex,
  obtenerSaldos,
  listarUbicaciones,
  registrarStockInicial,
  type CostoPromedio,
  type StockInicialDatos,
  type StockInicialResultado,
  type Ubicacion,
  type UbicacionCrearDatos,
  type UbicacionModificarDatos,
} from './api'
import { clavesCostoPromedio, clavesStock, type FiltrosKardex } from './claves'

/**
 * Lecturas y escrituras de stock (change 09, grupo 8, tarea 8.1). TanStack Query
 * solo en `/admin` (`CLAUDE.md` §2).
 *
 * El `Operation-Id` de cada envío se genera una sola vez en `onMutate` y se guarda
 * en un `ref`; `mutationFn` lo lee en cada intento, así el reintento automático
 * reenvía exactamente el mismo valor (INV-06). Quien necesita reusarlo entre dos
 * envíos manuales del mismo dato (reintento del usuario tras un corte de red) lo
 * pasa en `variables.operationId`. `retry` usa `debeReintentar`: solo un error de
 * RED, nunca un rechazo de dominio ya resuelto. Los tres comandos son `ONLINE`
 * puro: agotados los reintentos no se encola nada.
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

// --- lecturas ---------------------------------------------------------------

export function useUbicaciones(activo?: boolean) {
  return useInfiniteQuery({
    queryKey: clavesStock.ubicaciones(activo),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarUbicaciones(activo, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

/** Stock de una ubicación paginado por cursor ("cargar más"). */
export function useSaldos(ubicacionId: string) {
  return useInfiniteQuery({
    queryKey: clavesStock.saldos(ubicacionId),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => obtenerSaldos(ubicacionId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

/** Kardex paginado por cursor; el acumulado de cada página continúa el de la
 * anterior: lo calcula el servidor sobre la historia completa (D11). */
export function useKardex(productoId: string, ubicacionId: string, filtros: FiltrosKardex = {}) {
  return useInfiniteQuery({
    queryKey: clavesStock.kardex(productoId, ubicacionId, filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      obtenerKardex(productoId, ubicacionId, filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

/** Costo promedio y stock total (solo `VER_COSTOS`). `habilitado` en falso no
 * dispara ninguna consulta: quien no tiene el permiso nunca lo pide. */
export function useCostoPromedio(productoId: string | undefined, habilitado: boolean) {
  return useQuery<CostoPromedio, Error>({
    queryKey: clavesCostoPromedio.producto(productoId ?? ''),
    queryFn: () => obtenerCostoPromedio(productoId as string),
    enabled: habilitado && productoId !== undefined && productoId !== '',
  })
}

// --- escrituras -------------------------------------------------------------

function useMutacionConOperationId<Variables extends { operationId?: string }, Resultado>(
  ejecutar: (variables: Variables, operationId: string) => Promise<Resultado>,
  alAceptar: (resultado: Resultado, variables: Variables) => void,
) {
  const operationIdRef = useRef<string | null>(null)
  return useMutation<Resultado, Error, Variables>({
    retry: debeReintentar,
    retryDelay: 0,
    onMutate: (variables) => {
      operationIdRef.current = variables.operationId ?? generarOperationId()
    },
    mutationFn: (variables) => ejecutar(variables, operationIdRef.current ?? generarOperationId()),
    onSuccess: alAceptar,
  })
}

type VariablesCrearUbicacion = UbicacionCrearDatos & { operationId?: string }
type VariablesModificarUbicacion = UbicacionModificarDatos & { ubicacionId: string; operationId?: string }
type VariablesStockInicial = StockInicialDatos & { operationId?: string }

export function useCrearUbicacion() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesCrearUbicacion, Ubicacion>(
    (variables, operationId) =>
      crearUbicacion(
        { nombre: variables.nombre, tipo: variables.tipo, requiere_toma: variables.requiere_toma },
        operationId,
      ),
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesStock.raiz() })
    },
  )
}

export function useModificarUbicacion() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesModificarUbicacion, Ubicacion>(
    (variables, operationId) =>
      modificarUbicacion(
        variables.ubicacionId,
        {
          nombre: variables.nombre,
          tipo: variables.tipo,
          requiere_toma: variables.requiere_toma,
          activo: variables.activo,
        },
        operationId,
      ),
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesStock.raiz() })
    },
  )
}

export function useRegistrarStockInicial() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesStockInicial, StockInicialResultado>(
    (variables, operationId) =>
      registrarStockInicial({ ubicacion_id: variables.ubicacion_id, lineas: variables.lineas }, operationId),
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesStock.raiz() })
      void queryClient.invalidateQueries({ queryKey: clavesCostoPromedio.raiz() })
    },
  )
}
