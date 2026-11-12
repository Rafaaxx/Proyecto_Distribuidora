import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  crearMedioPago,
  listarMediosPagoAdmin,
  modificarMedioPago,
  type MedioPagoAdmin,
  type MedioPagoCrearDatos,
  type MedioPagoModificarDatos,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Administración de medios de pago (change 17b, D2, D4, D6). TanStack Query solo en `/admin`.
 * Mismo mecanismo de `Operation-Id` que compras: una vez por envío, y el reintento ante un error de
 * RED reenvía el mismo (INV-06); un rechazo de dominio no se reintenta. Al escribir se invalida
 * toda la raíz `['configuracion','medios-pago']`: la lista de administración y la de medios
 * activos que usan cobranzas, pagos y compras.
 */

export function useMediosPagoAdmin(habilitado = true) {
  return useQuery({
    queryKey: clavesConfiguracion.mediosPagoAdmin(),
    queryFn: listarMediosPagoAdmin,
    enabled: habilitado,
  })
}

type ConOperationId = { operationId?: string }
type VariablesCrear = MedioPagoCrearDatos & ConOperationId
type VariablesModificar = MedioPagoModificarDatos & { medioPagoId: string } & ConOperationId

function useInvalidarMedios() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.mediosPagoRaiz() })
  }
}

export function useCrearMedioPago() {
  const invalidar = useInvalidarMedios()
  return useMutacionConOperationId<VariablesCrear, MedioPagoAdmin>(({ operationId: _id, ...datos }, operationId) => {
    void _id
    return crearMedioPago(datos, operationId)
  }, invalidar)
}

export function useModificarMedioPago() {
  const invalidar = useInvalidarMedios()
  return useMutacionConOperationId<VariablesModificar, MedioPagoAdmin>(
    ({ medioPagoId, operationId: _id, ...datos }, operationId) => {
      void _id
      return modificarMedioPago(medioPagoId, datos, operationId)
    },
    invalidar,
  )
}
