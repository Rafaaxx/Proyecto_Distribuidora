import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import {
  cambiarCondicionIva,
  obtenerConfiguracionFiscal,
  obtenerResumenReglaIva,
  type CondicionIvaCambiarDatos,
  type ConfiguracionFiscal,
} from './api'
import { clavesConfiguracion } from './claves'

/**
 * Condición frente al IVA de la organización (11b, tarea 7.1, CST-06, `design.md` D7, D8,
 * D10). TanStack Query solo en `/admin` (`CLAUDE.md` §2).
 */

/** `GET /configuracion/fiscal`: lo puede leer cualquier usuario autenticado (D8). */
export function useConfiguracionFiscal() {
  return useQuery({
    queryKey: clavesConfiguracion.fiscal(),
    queryFn: obtenerConfiguracionFiscal,
  })
}

/** Costos vigentes con y sin crédito fiscal (D10). Solo se consulta cuando `habilitado`. */
export function useResumenReglaIva(habilitado: boolean) {
  return useQuery({
    queryKey: clavesConfiguracion.resumenReglaIva(),
    queryFn: obtenerResumenReglaIva,
    enabled: habilitado,
  })
}

/**
 * `ORGANIZACION_CONDICION_IVA_CAMBIAR`. El `Operation-Id` se genera una vez en `onMutate` y
 * `mutationFn` lo relee en cada intento: el reintento tras un error de red reenvía la misma
 * operación (INV-06); un rechazo de dominio no se reintenta (`debeReintentar`).
 */
export function useCambiarCondicionIva() {
  const queryClient = useQueryClient()
  const operationIdRef = useRef<string | null>(null)
  return useMutation<ConfiguracionFiscal, Error, CondicionIvaCambiarDatos>({
    retry: debeReintentar,
    retryDelay: 0,
    onMutate: () => {
      operationIdRef.current = generarOperationId()
    },
    mutationFn: (datos) => cambiarCondicionIva(datos, operationIdRef.current ?? generarOperationId()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.fiscal() })
      void queryClient.invalidateQueries({ queryKey: clavesConfiguracion.resumenReglaIva() })
    },
  })
}
