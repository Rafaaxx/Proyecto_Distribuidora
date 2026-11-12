import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { listarClientes, obtenerCliente, obtenerConsumidorFinal } from './api'
import { clavesClientes, type FiltrosClientes } from './claves'

/**
 * Lecturas de clientes (change 07, grupo 5, tarea 5.1). `useInfiniteQuery`
 * para el listado paginado por cursor (mismo criterio que
 * `features/proveedores/useListados.ts`); `useQuery` para el detalle y el
 * consumidor final.
 */

export function useClientes(filtros: FiltrosClientes = {}) {
  return useInfiniteQuery({
    queryKey: clavesClientes.clientes(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarClientes(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useCliente(clienteId: string | undefined) {
  return useQuery({
    queryKey: clavesClientes.cliente(clienteId ?? ''),
    queryFn: () => obtenerCliente(clienteId as string),
    enabled: clienteId !== undefined,
  })
}

/** `GET /clientes/consumidor-final` (spec `consumidor-final`): 200 con
 * `habilitado: false` cuando la organización no lo habilitó, nunca 404. */
export function useConsumidorFinal() {
  return useQuery({
    queryKey: clavesClientes.consumidorFinal(),
    queryFn: obtenerConsumidorFinal,
  })
}
