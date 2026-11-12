import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  configurarCreditoOrganizacion,
  configurarDescuentoManual,
  obtenerCreditoOrganizacion,
  obtenerDescuentoManual,
  type CreditoOrganizacion,
  type CreditoOrganizacionConfigurarDatos,
  type DescuentoManualConfig,
  type DescuentoManualConfigurarDatos,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Descuento manual y crédito por defecto de la organización (change 18b, D13, D14). TanStack
 * Query solo en `/admin`. Mismo mecanismo de `Operation-Id` que el resto de las escrituras: uno por
 * envío, el mismo en el reintento ante un error de red (INV-06). Al guardar se invalida lo que
 * lee "Nueva venta" (contexto y crédito de los clientes).
 */

export function useDescuentoManual() {
  return useQuery({ queryKey: clavesConfiguracion.descuentoManual(), queryFn: obtenerDescuentoManual })
}

export function useCreditoOrganizacion() {
  return useQuery({ queryKey: clavesConfiguracion.credito(), queryFn: obtenerCreditoOrganizacion })
}

type ConOperationId = { operationId?: string }

function useInvalidarTrasConfigurar() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.descuentoManual() })
    void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.credito() })
    void queryClient.invalidateQueries({ queryKey: ['ventas'] })
  }
}

export function useConfigurarDescuentoManual() {
  const invalidar = useInvalidarTrasConfigurar()
  return useMutacionConOperationId<DescuentoManualConfigurarDatos & ConOperationId, DescuentoManualConfig>(
    ({ operationId: _id, ...datos }, operationId) => {
      void _id
      return configurarDescuentoManual(datos, operationId)
    },
    invalidar,
  )
}

export function useConfigurarCreditoOrganizacion() {
  const invalidar = useInvalidarTrasConfigurar()
  return useMutacionConOperationId<CreditoOrganizacionConfigurarDatos & ConOperationId, CreditoOrganizacion>(
    ({ operationId: _id, ...datos }, operationId) => {
      void _id
      return configurarCreditoOrganizacion(datos, operationId)
    },
    invalidar,
  )
}
