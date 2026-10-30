import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  anularCobranza,
  listarCobranzas,
  listarOpcionesDeClientes,
  obtenerCobranza,
  obtenerSaldoDelCliente,
  registrarCobranza,
  type CobranzaAnularDatos,
  type CobranzaAnularResultado,
  type CobranzaRegistrarDatos,
  type CobranzaRegistrarResultado,
} from './api'
import { clavesCobranzas, clavesOpcionesDeClientes, clavesSaldoCliente, type FiltrosCobranzas } from './claves'

/**
 * Lecturas y escrituras de cobranzas (change 17, tarea 14.1). TanStack Query solo en `/admin`
 * (`CLAUDE.md` §2). Mismo mecanismo de `Operation-Id` que compras y pagos
 * (`useMutacionConOperationId`): se genera una vez por envío y el reintento automático ante un
 * error de RED reenvía exactamente el mismo valor (INV-06); un rechazo de dominio no se
 * reintenta. Desde `/admin` los comandos de cobranza son `ONLINE`: no se encola nada.
 */

export function useCobranzas(filtros: FiltrosCobranzas = {}) {
  return useInfiniteQuery({
    queryKey: clavesCobranzas.listado(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarCobranzas(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useCobranza(cobranzaId: string | undefined) {
  return useQuery({
    queryKey: clavesCobranzas.detalle(cobranzaId ?? ''),
    queryFn: () => obtenerCobranza(cobranzaId as string),
    enabled: cobranzaId !== undefined,
  })
}

/** Selector de clientes de quien cobra; `texto` filtra por nombre o código (`GET /clientes/opciones`). */
export function useOpcionesDeClientes(texto = '', incluirConsumidorFinal = false, buscarEnTodos = false) {
  return useInfiniteQuery({
    queryKey: clavesOpcionesDeClientes.texto(texto, incluirConsumidorFinal, buscarEnTodos),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listarOpcionesDeClientes(texto, pageParam, undefined, incluirConsumidorFinal, buscarEnTodos),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

/** Saldo actual del cliente (string de la API). Sin id no pide nada. */
export function useSaldoDelCliente(clienteId: string | undefined) {
  return useQuery({
    queryKey: clavesSaldoCliente.cliente(clienteId ?? ''),
    queryFn: () => obtenerSaldoDelCliente(clienteId as string),
    enabled: clienteId !== undefined,
  })
}

type VariablesRegistrarCobranza = CobranzaRegistrarDatos & { operationId?: string }
type VariablesAnularCobranza = CobranzaAnularDatos & { cobranzaId: string; operationId?: string }

function useInvalidarTrasMoverCobranzas() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesCobranzas.raiz() })
    void queryClient.invalidateQueries({ queryKey: clavesSaldoCliente.raiz() })
    void queryClient.invalidateQueries({ queryKey: ['cuentas-corrientes'] })
  }
}

/** Registrar mueve las cobranzas, el saldo del cliente y su estado de cuenta. */
export function useRegistrarCobranza() {
  const invalidar = useInvalidarTrasMoverCobranzas()
  return useMutacionConOperationId<VariablesRegistrarCobranza, CobranzaRegistrarResultado>((variables, operationId) => {
    const datos: CobranzaRegistrarDatos & { operationId?: string } = { ...variables }
    delete datos.operationId
    return registrarCobranza(datos, operationId)
  }, invalidar)
}

export function useAnularCobranza() {
  const invalidar = useInvalidarTrasMoverCobranzas()
  return useMutacionConOperationId<VariablesAnularCobranza, CobranzaAnularResultado>(
    (variables, operationId) =>
      anularCobranza(
        variables.cobranzaId,
        { motivo_id: variables.motivo_id, observacion: variables.observacion ?? null },
        operationId,
      ),
    invalidar,
  )
}
