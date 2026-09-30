import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import type { CuentaTipo } from '../../domain/cuentas-corrientes/presentacion'
import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import {
  obtenerEstadoDeCuenta,
  registrarSaldoInicial,
  type SaldoInicialDatos,
  type SaldoInicialResultado,
} from './api'
import { clavesCuentasCorrientes, type FiltrosEstadoDeCuenta } from './claves'

/**
 * Lecturas y escritura de cuentas corrientes (change 08, grupo 7, tarea 7.1).
 * TanStack Query solo en `/admin` (`CLAUDE.md` §2).
 *
 * El `Operation-Id` de cada envío del saldo inicial se genera una sola vez en
 * `onMutate` (una vez por `.mutate(...)`, antes de cualquier intento) y se
 * guarda en un `ref`; `mutationFn` lo lee en cada intento, así el reintento
 * automático reenvía exactamente el mismo valor (INV-06). Quien necesita reusar
 * el valor entre dos envíos manuales del mismo dato (reintento del usuario tras
 * un corte de red) lo pasa en `variables.operationId`. `retry` usa
 * `debeReintentar`: solo un error de RED, nunca un rechazo de dominio ya
 * resuelto. `SALDO_INICIAL_REGISTRAR` es `ONLINE` puro: agotados los reintentos
 * no se encola nada, la pantalla solo avisa que hace falta conexión.
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

/** Estado de cuenta paginado por cursor (`useInfiniteQuery`, "cargar más"). El
 * saldo acumulado de cada página continúa el de la anterior: lo calcula el
 * servidor sobre la cuenta completa (CC-07, D9). */
export function useEstadoDeCuenta(cuentaTipo: CuentaTipo, entidadId: string, filtros: FiltrosEstadoDeCuenta = {}) {
  return useInfiniteQuery({
    queryKey: clavesCuentasCorrientes.estadoDeCuenta(cuentaTipo, entidadId, filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      obtenerEstadoDeCuenta(cuentaTipo, entidadId, filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

/** Saldo actual de la cuenta para la ficha (tarea 7.2): se lee del mismo
 * estado de cuenta pidiendo una sola fila, así la ficha no necesita un
 * endpoint ni un campo nuevo. Devuelve el string de la API (INV-03). */
export function useSaldoActual(cuentaTipo: CuentaTipo, entidadId: string) {
  return useQuery({
    queryKey: clavesCuentasCorrientes.saldo(cuentaTipo, entidadId),
    queryFn: async () => (await obtenerEstadoDeCuenta(cuentaTipo, entidadId, {}, undefined, 1)).saldo_actual,
  })
}

type VariablesSaldoInicial = SaldoInicialDatos & { operationId?: string }

export function useRegistrarSaldoInicial() {
  const queryClient = useQueryClient()
  const operationIdRef = useRef<string | null>(null)
  return useMutation<SaldoInicialResultado, Error, VariablesSaldoInicial>({
    retry: debeReintentar,
    retryDelay: 0,
    onMutate: (variables) => {
      operationIdRef.current = variables.operationId ?? generarOperationId()
    },
    mutationFn: (variables) =>
      registrarSaldoInicial(
        {
          cuenta_tipo: variables.cuenta_tipo,
          entidad_id: variables.entidad_id,
          importe: variables.importe,
          sentido: variables.sentido,
        },
        operationIdRef.current ?? generarOperationId(),
      ),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({
        queryKey: clavesCuentasCorrientes.entidad(variables.cuenta_tipo, variables.entidad_id),
      })
    },
  })
}
