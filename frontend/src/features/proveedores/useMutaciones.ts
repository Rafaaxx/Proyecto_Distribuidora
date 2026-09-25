import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import {
  crearProveedor,
  informarCostos,
  modificarProveedor,
  type CostoInformarDatos,
  type CostoInformarResultado,
  type Proveedor,
  type ProveedorCrearDatos,
  type ProveedorModificarDatos,
} from './api'
import { clavesProveedores } from './claves'

/**
 * Mutaciones de escritura de proveedores y costos (tarea 11.2).
 *
 * El `Operation-Id` de cada envío se genera una sola vez en `onMutate`
 * (que TanStack Query ejecuta una única vez por llamada a `.mutate(...)`,
 * antes de cualquier intento) y se guarda en un `ref`; `mutationFn` lo lee
 * de ahí en cada intento. El reintento automático de TanStack Query
 * (`retry`) vuelve a invocar `mutationFn` con las mismas variables pero
 * SIN volver a llamar `onMutate`, así que el reintento reenvía exactamente
 * el mismo `Operation-Id` (INV-06, `design.md` D10) -- generarlo dentro de
 * `mutationFn` en cambio produciría uno distinto en cada intento. Mismo
 * criterio que `features/catalogo/useMutacionesCatalogo.ts`.
 *
 * `retry` usa `debeReintentar` (`lib/api/reintentoDeRed.ts`) en vez de un
 * número fijo: solo reintenta un error de RED (nunca llegó a haber una
 * respuesta HTTP), no un rechazo de dominio ya resuelto por el servidor
 * (409/422 con `codigo`) -- bug de la verificación manual 13.5, corregido
 * en la tarea 14.2.
 */

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

// --- Proveedores ---

interface VariablesCrearProveedor extends ProveedorCrearDatos {
  operationId?: string
}

export function useCrearProveedor() {
  const invalidar = useInvalidar([clavesProveedores.proveedores(), clavesProveedores.opciones()])
  return useMutacionConOperationId<VariablesCrearProveedor, Proveedor>({
    ejecutar: ({ nombre, cuit, contacto, telefono, email }, operationId) =>
      crearProveedor({ nombre, cuit, contacto, telefono, email }, operationId),
    onSuccess: invalidar,
  })
}

interface VariablesModificarProveedor extends ProveedorModificarDatos {
  proveedorId: string
  operationId?: string
}

export function useModificarProveedor() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesModificarProveedor, Proveedor>({
    ejecutar: ({ proveedorId, nombre, cuit, contacto, telefono, email, activo }, operationId) =>
      modificarProveedor(proveedorId, { nombre, cuit, contacto, telefono, email, activo }, operationId),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesProveedores.proveedores() })
      void queryClient.invalidateQueries({ queryKey: clavesProveedores.opciones() })
      void queryClient.invalidateQueries({ queryKey: clavesProveedores.proveedor(variables.proveedorId) })
    },
  })
}

// --- Costos informados ---

interface VariablesInformarCostos extends CostoInformarDatos {
  operationId?: string
}

export function useInformarCostos() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesInformarCostos, CostoInformarResultado>({
    ejecutar: ({ proveedor_id, costos }, operationId) => informarCostos({ proveedor_id, costos }, operationId),
    onSuccess: (_resultado, variables) => {
      // CST-05: un lote puede tocar varios productos -- se invalida el
      // vigente y el historial de cada uno de los productos informados.
      for (const costo of variables.costos) {
        void queryClient.invalidateQueries({
          queryKey: clavesProveedores.historialDeCostos(costo.producto_id),
        })
        void queryClient.invalidateQueries({
          predicate: (query) =>
            query.queryKey[0] === 'proveedores' &&
            query.queryKey[1] === 'costos' &&
            query.queryKey[2] === 'vigente' &&
            query.queryKey[3] === costo.producto_id,
        })
      }
    },
  })
}
