import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  crearMotivo,
  listarMotivosAdmin,
  modificarMotivo,
  type MotivoAdmin,
  type MotivoCrearDatos,
  type MotivoModificarDatos,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Administración de motivos (change 20c, D2, D4, D12). TanStack Query solo en `/admin`. Un
 * `Operation-Id` por envío, el mismo en el reintento ante un error de red (INV-06). Al escribir se
 * invalida toda la raíz `['configuracion','motivos']`: la lista de administración y los motivos
 * activos por ámbito que ofrecen ajustes, anulaciones y descuentos.
 */

export function useMotivosAdmin(ambito: string) {
  return useQuery({
    queryKey: clavesConfiguracion.motivosAdmin(ambito),
    queryFn: () => listarMotivosAdmin(ambito),
  })
}

type ConOperationId = { operationId?: string }
type VariablesCrear = MotivoCrearDatos & ConOperationId
type VariablesModificar = MotivoModificarDatos & { motivoId: string } & ConOperationId

function useInvalidarMotivos() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.motivosRaiz() })
  }
}

export function useCrearMotivo() {
  const invalidar = useInvalidarMotivos()
  return useMutacionConOperationId<VariablesCrear, MotivoAdmin>(({ operationId: _id, ...datos }, operationId) => {
    void _id
    return crearMotivo(datos, operationId)
  }, invalidar)
}

export function useModificarMotivo() {
  const invalidar = useInvalidarMotivos()
  return useMutacionConOperationId<VariablesModificar, MotivoAdmin>(
    ({ motivoId, operationId: _id, ...datos }, operationId) => {
      void _id
      return modificarMotivo(motivoId, datos, operationId)
    },
    invalidar,
  )
}
