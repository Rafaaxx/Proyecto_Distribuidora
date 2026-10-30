import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  definirRedondeoPorDefecto,
  obtenerRedondeoPorDefecto,
  type RedondeoPorDefecto,
  type RedondeoPorDefectoDatos,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Redondeo por defecto de la organización (change 20c, D10, D11). Lo leen la pantalla de
 * configuración y el formulario de lista nueva (`habilitado` evita pedirlo en la edición).
 * Un `Operation-Id` por envío, el mismo en el reintento ante un error de red (INV-06).
 */

export function useRedondeoPorDefecto(habilitado = true) {
  return useQuery({
    queryKey: clavesConfiguracion.redondeoPorDefecto(),
    queryFn: obtenerRedondeoPorDefecto,
    enabled: habilitado,
  })
}

export function useDefinirRedondeoPorDefecto() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<RedondeoPorDefectoDatos & { operationId?: string }, RedondeoPorDefecto>(
    ({ operationId: _id, ...datos }, operationId) => {
      void _id
      return definirRedondeoPorDefecto(datos, operationId)
    },
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.redondeoPorDefecto() })
    },
  )
}
