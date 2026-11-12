import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  configurarOrganizacionDatos,
  obtenerOrganizacionDatos,
  type OrganizacionDatos,
  type OrganizacionDatosConfigurar,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Nombre y CUIT de la organización (change 20, D15). TanStack Query solo en `/admin`. Un
 * `Operation-Id` por envío, el mismo en el reintento ante un error de red (INV-06). Al guardar se
 * invalida la propia lectura y las notas ya leídas (su encabezado lleva el nombre y el CUIT).
 */

export function useDatosOrganizacion() {
  return useQuery({ queryKey: clavesConfiguracion.datosOrganizacion(), queryFn: obtenerOrganizacionDatos })
}

export function useConfigurarDatosOrganizacion() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<OrganizacionDatosConfigurar & { operationId?: string }, OrganizacionDatos>(
    ({ operationId: _id, ...datos }, operationId) => {
      void _id
      return configurarOrganizacionDatos(datos, operationId)
    },
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.datosOrganizacion() })
      void queryClient.invalidateQueries({ queryKey: ['ventas', 'nota'] })
    },
  )
}
