import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import {
  configurarConsumidorFinal,
  crearCliente,
  modificarCliente,
  modificarCreditoCliente,
  type Cliente,
  type ClienteCreditoModificarDatos,
  type ClienteCrearDatos,
  type ClienteModificarDatos,
  type ConsumidorFinalConfigurarDatos,
} from './api'
import { clavesClientes } from './claves'

/**
 * Mutaciones de escritura de clientes (change 07, grupo 5, tareas 5.3, 5.4
 * y 5.5; `design.md` D9 enmienda 2026-09-29).
 *
 * El `Operation-Id` de cada envío se genera una sola vez en `onMutate` (que
 * TanStack Query ejecuta una única vez por llamada a `.mutate(...)`, antes
 * de cualquier intento) y se guarda en un `ref`; `mutationFn` lo lee de ahí
 * en cada intento -- así el reintento automático de TanStack Query (`retry`)
 * reenvía exactamente el mismo `Operation-Id` (INV-06, `design.md` D10).
 * Mismo criterio que `features/proveedores/useMutaciones.ts` y
 * `features/catalogo/useMutacionesCatalogo.ts`.
 *
 * `retry` usa `debeReintentar`: solo reintenta un error de RED (la petición
 * nunca llegó a producir una respuesta HTTP), nunca un rechazo de dominio ya
 * resuelto por el servidor (403/404/409/422 con `codigo`). Los cuatro
 * comandos de este módulo son `ONLINE` puros (`admite_offline=False`): un
 * error de red agotados los reintentos NO se encola para reenviar más
 * tarde -- el `/admin` no tiene cola offline (esa es responsabilidad del
 * área `/ruta`, `Dexie`, fuera del alcance de este change) -- la pantalla
 * solo avisa que hace falta conexión (`esErrorDeRed`, re-exportado acá para
 * que las pantallas no importen `lib/api/reintentoDeRed` directamente).
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

function useMutacionConOperationId<TVariables extends { operationId?: string }, TResultado>(opciones: {
  ejecutar: (variables: TVariables, operationId: string) => Promise<TResultado>
  onSuccess?: (resultado: TResultado, variables: TVariables) => void
}) {
  const operationIdRef = useRef<string | null>(null)
  return useMutation<TResultado, Error, TVariables>({
    retry: debeReintentar,
    retryDelay: 0,
    onMutate: (variables) => {
      operationIdRef.current = variables.operationId ?? generarOperationId()
    },
    mutationFn: (variables) => opciones.ejecutar(variables, operationIdRef.current ?? generarOperationId()),
    onSuccess: opciones.onSuccess,
  })
}

function useInvalidar(clavesAInvalidar: QueryKey[]) {
  const queryClient = useQueryClient()
  return () => {
    for (const clave of clavesAInvalidar) {
      void queryClient.invalidateQueries({ queryKey: clave })
    }
  }
}

// --- Ficha (D3: sin campos de crédito) --------------------------------------

interface VariablesCrearCliente extends ClienteCrearDatos {
  operationId?: string
}

export function useCrearCliente() {
  const invalidar = useInvalidar([clavesClientes.clientes()])
  return useMutacionConOperationId<VariablesCrearCliente, Cliente>({
    ejecutar: (datos, operationId) => crearCliente(datos, operationId),
    onSuccess: invalidar,
  })
}

interface VariablesModificarCliente extends ClienteModificarDatos {
  clienteId: string
  operationId?: string
}

export function useModificarCliente() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesModificarCliente, Cliente>({
    ejecutar: ({ clienteId, ...datos }, operationId) => modificarCliente(clienteId, datos, operationId),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesClientes.clientes() })
      void queryClient.invalidateQueries({ queryKey: clavesClientes.cliente(variables.clienteId) })
    },
  })
}

// --- Crédito (D3, D8) --------------------------------------------------------

interface VariablesModificarCreditoCliente extends ClienteCreditoModificarDatos {
  clienteId: string
  operationId?: string
}

export function useModificarCreditoCliente() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesModificarCreditoCliente, Cliente>({
    ejecutar: ({ clienteId, ...datos }, operationId) => modificarCreditoCliente(clienteId, datos, operationId),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesClientes.clientes() })
      void queryClient.invalidateQueries({ queryKey: clavesClientes.cliente(variables.clienteId) })
    },
  })
}

// --- Consumidor final (D4, ADR-029) ------------------------------------------

interface VariablesConfigurarConsumidorFinal extends ConsumidorFinalConfigurarDatos {
  operationId?: string
}

export function useConfigurarConsumidorFinal() {
  const invalidar = useInvalidar([clavesClientes.consumidorFinal(), clavesClientes.clientes()])
  return useMutacionConOperationId<VariablesConfigurarConsumidorFinal, Cliente>({
    ejecutar: (datos, operationId) => configurarConsumidorFinal(datos, operationId),
    onSuccess: invalidar,
  })
}
