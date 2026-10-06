import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'

import { clavesCompras } from '../compras/claves'
import { useMutacionConOperationId } from '../compras/hooks'
import {
  anularPago,
  listarPagos,
  obtenerPago,
  obtenerSaldoDelProveedor,
  registrarPago,
  type PagoAnularDatos,
  type PagoAnularResultado,
  type PagoRegistrarDatos,
  type PagoRegistrarResultado,
} from './api'
import { clavesPagos, clavesSaldoProveedor, type FiltrosPagos } from './claves'

/**
 * Lecturas y escrituras de pagos a proveedores (change 12, tarea 8.2). TanStack Query solo
 * en `/admin` (`CLAUDE.md` §2). Mismo mecanismo de `Operation-Id` que compras
 * (`useMutacionConOperationId`): se genera una vez por envío y el reintento automático ante
 * un error de RED reenvía exactamente el mismo valor (INV-06); un rechazo de dominio no se
 * reintenta. `PAGO_PROVEEDOR_REGISTRAR` y `PAGO_PROVEEDOR_ANULAR` son `ONLINE` puros: no se
 * encola nada.
 */

export function usePagos(filtros: FiltrosPagos = {}) {
  return useInfiniteQuery({
    queryKey: clavesPagos.listado(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarPagos(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function usePago(pagoId: string | undefined) {
  return useQuery({
    queryKey: clavesPagos.detalle(pagoId ?? ''),
    queryFn: () => obtenerPago(pagoId as string),
    enabled: pagoId !== undefined,
  })
}

/** Saldo actual del proveedor (string de la API, D8). Sin id no pide nada. */
export function useSaldoDelProveedor(proveedorId: string | undefined) {
  return useQuery({
    queryKey: clavesSaldoProveedor.proveedor(proveedorId ?? ''),
    queryFn: () => obtenerSaldoDelProveedor(proveedorId as string),
    enabled: proveedorId !== undefined,
  })
}

type VariablesRegistrarPago = PagoRegistrarDatos & { operationId?: string }
type VariablesAnularPago = PagoAnularDatos & { pagoId: string; operationId?: string }

function useInvalidarTrasMoverPagos(tocaCompras: boolean) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesPagos.raiz() })
    void queryClient.invalidateQueries({ queryKey: clavesSaldoProveedor.raiz() })
    void queryClient.invalidateQueries({ queryKey: ['cuentas-corrientes'] })
    if (tocaCompras) void queryClient.invalidateQueries({ queryKey: clavesCompras.raiz() })
  }
}

/** Registrar mueve los pagos, el saldo del proveedor y su estado de cuenta. */
export function useRegistrarPago() {
  const invalidar = useInvalidarTrasMoverPagos(false)
  return useMutacionConOperationId<VariablesRegistrarPago, PagoRegistrarResultado>((variables, operationId) => {
    const datos: PagoRegistrarDatos = { ...variables }
    delete (datos as PagoRegistrarDatos & { operationId?: string }).operationId
    return registrarPago(datos, operationId)
  }, invalidar)
}

/** Anular además refresca las compras: el detalle de una compra muestra el estado de su pago. */
export function useAnularPago() {
  const invalidar = useInvalidarTrasMoverPagos(true)
  return useMutacionConOperationId<VariablesAnularPago, PagoAnularResultado>(
    (variables, operationId) => anularPago(variables.pagoId, { motivo_id: variables.motivo_id }, operationId),
    invalidar,
  )
}
