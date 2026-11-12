import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import { configurarNotaVenta, obtenerNotaVentaConfig, type NotaVentaConfig, type NotaVentaConfigurarDatos } from './api'
import { clavesConfiguracion } from './claves'

/**
 * Parámetros de la nota de venta de la organización (change 20, D10). TanStack Query solo en
 * `/admin`. Un `Operation-Id` por envío, el mismo en el reintento ante un error de red (INV-06).
 * Al guardar se invalida la propia configuración y las notas ya leídas (llevan el saldo y los datos
 * de la organización).
 */

export function useNotaVentaConfig() {
  return useQuery({ queryKey: clavesConfiguracion.notaVenta(), queryFn: obtenerNotaVentaConfig })
}

export function useConfigurarNotaVenta() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<NotaVentaConfigurarDatos & { operationId?: string }, NotaVentaConfig>(
    ({ operationId: _id, ...datos }, operationId) => {
      void _id
      return configurarNotaVenta(datos, operationId)
    },
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.notaVenta() })
      void queryClient.invalidateQueries({ queryKey: ['ventas', 'nota'] })
    },
  )
}
