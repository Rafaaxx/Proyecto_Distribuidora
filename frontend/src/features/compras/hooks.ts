import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import { clavesCostoPromedio, clavesStock } from '../stock/claves'
import {
  anularCompra,
  confirmarCompra,
  listarCompras,
  listarMediosPago,
  listarMotivos,
  obtenerCompra,
  type CompraAnularDatos,
  type CompraAnularResultado,
  type CompraConfirmarDatos,
  type CompraConfirmarResultado,
} from './api'
import { clavesCompras, clavesConfiguracionDeCompras, type FiltrosCompras } from './claves'

/**
 * Lecturas y escrituras de compras (change 11, tarea 11.1). TanStack Query solo en `/admin`
 * (`CLAUDE.md` §2).
 *
 * El `Operation-Id` de cada envío se genera una sola vez en `onMutate` y se guarda en un
 * `ref`; `mutationFn` lo lee en cada intento, así el reintento automático reenvía
 * exactamente el mismo valor (INV-06). Quien necesita reusarlo entre dos envíos manuales
 * del mismo contenido (reintento del usuario tras un corte de red) lo pasa en
 * `variables.operationId` -- ver `useOperationIdPorContenido`. `retry` usa
 * `debeReintentar`: solo un error de RED, nunca un rechazo de dominio ya resuelto.
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

// --- lecturas ---------------------------------------------------------------

export function useCompras(filtros: FiltrosCompras = {}) {
  return useInfiniteQuery({
    queryKey: clavesCompras.listado(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarCompras(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useCompra(compraId: string | undefined) {
  return useQuery({
    queryKey: clavesCompras.detalle(compraId ?? ''),
    queryFn: () => obtenerCompra(compraId as string),
    enabled: compraId !== undefined,
  })
}

/** Medios de pago activos (`GET /configuracion/medios-pago`, D8, D14). */
export function useMediosPago() {
  return useQuery({ queryKey: clavesConfiguracionDeCompras.mediosPago(), queryFn: listarMediosPago })
}

/** Motivos activos de un ámbito, p. ej. `ANULACION_COMPRA` (D2, D8). */
export function useMotivos(ambito: string) {
  return useQuery({
    queryKey: clavesConfiguracionDeCompras.motivos(ambito),
    queryFn: () => listarMotivos(ambito),
  })
}

// --- escrituras -------------------------------------------------------------

export function useMutacionConOperationId<Variables extends { operationId?: string }, Resultado>(
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

type VariablesConfirmarCompra = CompraConfirmarDatos & { operationId?: string }
type VariablesAnularCompra = CompraAnularDatos & { compraId: string; operationId?: string }

function useInvalidarTrasMoverCompras() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesCompras.raiz() })
    void queryClient.invalidateQueries({ queryKey: clavesStock.raiz() })
    void queryClient.invalidateQueries({ queryKey: clavesCostoPromedio.raiz() })
    void queryClient.invalidateQueries({ queryKey: ['cuentas-corrientes'] })
  }
}

/** Confirmar mueve compras, stock, costo promedio y la cuenta del proveedor. */
export function useConfirmarCompra() {
  const invalidar = useInvalidarTrasMoverCompras()
  return useMutacionConOperationId<VariablesConfirmarCompra, CompraConfirmarResultado>(
    (variables, operationId) => {
      const datos: CompraConfirmarDatos = { ...variables }
      delete (datos as CompraConfirmarDatos & { operationId?: string }).operationId
      return confirmarCompra(datos, operationId)
    },
    invalidar,
  )
}

export function useAnularCompra() {
  const invalidar = useInvalidarTrasMoverCompras()
  return useMutacionConOperationId<VariablesAnularCompra, CompraAnularResultado>(
    (variables, operationId) =>
      anularCompra(
        variables.compraId,
        {
          motivo_id: variables.motivo_id,
          ...(variables.devuelve_pago === undefined ? {} : { devuelve_pago: variables.devuelve_pago }),
        },
        operationId,
      ),
    invalidar,
  )
}
