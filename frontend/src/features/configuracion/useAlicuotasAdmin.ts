import { useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  crearAlicuota,
  modificarAlicuota,
  type Alicuota,
  type AlicuotaCrearDatos,
  type AlicuotaModificarDatos,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Escrituras de alícuotas (change 20c, D6, D8, D12). El listado es `useAlicuotas` (el mismo que usa el
 * formulario de productos); al escribir se invalida su clave para que ambos se relean. Un
 * `Operation-Id` por envío, el mismo en el reintento ante un error de red (INV-06).
 */

type ConOperationId = { operationId?: string }
type VariablesCrear = AlicuotaCrearDatos & ConOperationId
type VariablesModificar = AlicuotaModificarDatos & { alicuotaId: string } & ConOperationId

function useInvalidarAlicuotas() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.alicuotas() })
  }
}

export function useCrearAlicuota() {
  const invalidar = useInvalidarAlicuotas()
  return useMutacionConOperationId<VariablesCrear, Alicuota>(({ operationId: _id, ...datos }, operationId) => {
    void _id
    return crearAlicuota(datos, operationId)
  }, invalidar)
}

export function useModificarAlicuota() {
  const invalidar = useInvalidarAlicuotas()
  return useMutacionConOperationId<VariablesModificar, Alicuota>(
    ({ alicuotaId, operationId: _id, ...datos }, operationId) => {
      void _id
      return modificarAlicuota(alicuotaId, datos, operationId)
    },
    invalidar,
  )
}
