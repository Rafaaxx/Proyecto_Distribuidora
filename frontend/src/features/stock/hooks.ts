import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import { useMotivos } from '../compras/hooks'
import {
  anularAjuste,
  anularTransferencia,
  crearUbicacion,
  listarAjustes,
  listarTransferencias,
  modificarUbicacion,
  obtenerAjuste,
  obtenerTransferencia,
  registrarAjuste,
  registrarTransferencia,
  obtenerCostoPromedio,
  obtenerKardex,
  obtenerSaldos,
  listarUbicaciones,
  registrarStockInicial,
  type AjusteAnuladoResultado,
  type AjusteDatos,
  type AjusteDetalle,
  type AjusteResultado,
  type CostoPromedio,
  type LineaDeStock,
  type StockInicialDatos,
  type StockInicialResultado,
  type TransferenciaAnuladaResultado,
  type TransferenciaDatos,
  type TransferenciaDetalle,
  type TransferenciaResultado,
  type Ubicacion,
  type UbicacionCrearDatos,
  type UbicacionModificarDatos,
} from './api'
import {
  clavesCostoPromedio,
  clavesStock,
  type FiltrosAjustes,
  type FiltrosKardex,
  type FiltrosTransferencias,
} from './claves'

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

/** Ámbitos de motivo de stock (lista cerrada del servidor): ajuste y las dos anulaciones. */
export type AmbitoDeMotivoDeStock = 'AJUSTE_STOCK' | 'ANULACION_TRANSFERENCIA' | 'ANULACION_AJUSTE'

/** Motivos activos de un ámbito de stock. Comparte la caché de `useMotivos` (`ADR-043`). */
export function useMotivosDeStock(ambito: AmbitoDeMotivoDeStock) {
  return useMotivos(ambito)
}

export interface SaldosCompletos {
  lineas: LineaDeStock[]
  /** Falso mientras falten páginas; el selector y los saldos actuales se muestran con todas. */
  completo: boolean
  error: unknown
}

/**
 * Todos los saldos de una ubicación: sigue pidiendo páginas hasta agotar el cursor. La
 * transferencia elige sus productos del stock del origen (`design.md` D7) y necesita el saldo
 * actual de cada uno en origen y destino. Sin ubicación no pide nada.
 */
export function useSaldosCompletos(ubicacionId: string | undefined): SaldosCompletos {
  const consulta = useInfiniteQuery({
    queryKey: clavesStock.saldos(ubicacionId ?? ''),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => obtenerSaldos(ubicacionId as string, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
    enabled: ubicacionId !== undefined && ubicacionId !== '',
  })
  const { hasNextPage, isFetchingNextPage, isError, fetchNextPage } = consulta
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && !isError) void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, isError, fetchNextPage])

  const lineas = consulta.data?.pages.flatMap((pagina) => pagina.items) ?? []
  return { lineas, completo: consulta.isSuccess && !hasNextPage, error: consulta.error }
}

// --- transferencias y ajustes -------------------------------------------------

export function useTransferencias(filtros: FiltrosTransferencias) {
  return useInfiniteQuery({
    queryKey: clavesStock.transferencias(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarTransferencias(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useTransferencia(id: string | undefined) {
  return useQuery<TransferenciaDetalle, Error>({
    queryKey: clavesStock.transferencia(id ?? ''),
    queryFn: () => obtenerTransferencia(id as string),
    enabled: id !== undefined && id !== '',
  })
}

export function useAjustes(filtros: FiltrosAjustes) {
  return useInfiniteQuery({
    queryKey: clavesStock.ajustes(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarAjustes(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useAjuste(id: string | undefined) {
  return useQuery<AjusteDetalle, Error>({
    queryKey: clavesStock.ajuste(id ?? ''),
    queryFn: () => obtenerAjuste(id as string),
    enabled: id !== undefined && id !== '',
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

// --- transferencias y ajustes (change 14) -------------------------------------

type VariablesTransferencia = TransferenciaDatos & { operationId?: string }
type VariablesAjuste = AjusteDatos & { operationId?: string }
type VariablesAnulacion = { id: string; motivo_id: string; operationId?: string }

/** Una transferencia o un ajuste cambian saldos, kardex, listados, detalles y el stock total del costeo. */
function useInvalidarStockYCostos() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesStock.raiz() })
    void queryClient.invalidateQueries({ queryKey: clavesCostoPromedio.raiz() })
  }
}

export function useRegistrarTransferencia() {
  const invalidar = useInvalidarStockYCostos()
  return useMutacionConOperationId<VariablesTransferencia, TransferenciaResultado>(
    (variables, operationId) =>
      registrarTransferencia(
        {
          ubicacion_origen_id: variables.ubicacion_origen_id,
          ubicacion_destino_id: variables.ubicacion_destino_id,
          lineas: variables.lineas,
          ...(variables.observacion === undefined ? {} : { observacion: variables.observacion }),
        },
        operationId,
      ),
    invalidar,
  )
}

export function useAnularTransferencia() {
  const invalidar = useInvalidarStockYCostos()
  return useMutacionConOperationId<VariablesAnulacion, TransferenciaAnuladaResultado>(
    (variables, operationId) => anularTransferencia(variables.id, variables.motivo_id, operationId),
    invalidar,
  )
}

export function useRegistrarAjuste() {
  const invalidar = useInvalidarStockYCostos()
  return useMutacionConOperationId<VariablesAjuste, AjusteResultado>(
    (variables, operationId) =>
      registrarAjuste(
        {
          ubicacion_id: variables.ubicacion_id,
          motivo_id: variables.motivo_id,
          lineas: variables.lineas,
          ...(variables.observacion === undefined ? {} : { observacion: variables.observacion }),
        },
        operationId,
      ),
    invalidar,
  )
}

export function useAnularAjuste() {
  const invalidar = useInvalidarStockYCostos()
  return useMutacionConOperationId<VariablesAnulacion, AjusteAnuladoResultado>(
    (variables, operationId) => anularAjuste(variables.id, variables.motivo_id, operationId),
    invalidar,
  )
}
