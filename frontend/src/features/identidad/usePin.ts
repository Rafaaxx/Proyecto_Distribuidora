import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, type MutableRefObject } from 'react'

import { useMutacionConOperationId } from '../compras/hooks'
import { clavesIdentidad } from './claves'
import {
  definirMiPin,
  listarUsuarios,
  obtenerEstadoDeMiPin,
  rotarPinDeUsuario,
} from './pinApi'

/**
 * PIN de autorización y "Mi PIN" (change 18b, D21). TanStack Query solo en `/admin`.
 *
 * Los secretos (el PIN y la contraseña) NO viajan en las variables de la mutación -que TanStack
 * Query conserva en memoria- ni entran a la caché: los entrega una referencia (`useSecretoEfimero`)
 * que quien llama llena justo antes de enviar y vacía al terminar, salga como salga (D21 punto 9).
 * El `Operation-Id` lo conserva quien llama: un reintento tras un rechazo con los datos corregidos
 * usa el mismo (el rechazo no deja fila de `comando`, D21 punto 5 b).
 */

export interface SecretoEfimero<T> {
  ref: MutableRefObject<T | null>
  /** Guarda `valor` mientras dura `accion` y lo borra al terminar, con éxito o con error. */
  usar: <R>(valor: T, accion: () => Promise<R>) => Promise<R>
}

export function useSecretoEfimero<T>(): SecretoEfimero<T> {
  const ref = useRef<T | null>(null)
  const usar = async <R,>(valor: T, accion: () => Promise<R>): Promise<R> => {
    ref.current = valor
    try {
      return await accion()
    } finally {
      ref.current = null
    }
  }
  return { ref, usar }
}

export function useUsuarios(habilitado = true) {
  return useQuery({ queryKey: clavesIdentidad.usuarios(), queryFn: listarUsuarios, enabled: habilitado })
}

export function useEstadoDeMiPin(habilitado = true) {
  return useQuery({
    queryKey: clavesIdentidad.miPin(),
    queryFn: obtenerEstadoDeMiPin,
    enabled: habilitado,
    staleTime: 0,
    retry: false,
  })
}

type VariablesRotar = { usuarioId: string; operationId?: string }

/** `PIN_AUTORIZACION_ROTAR`: al terminar se relee la lista (`tiene_pin_autorizacion`). */
export function useRotarPin(leerPin: () => string) {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesRotar, void>(
    ({ usuarioId }, operationId) => rotarPinDeUsuario(usuarioId, leerPin(), operationId),
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesIdentidad.usuarios() })
    },
  )
}

type VariablesMiPin = { operationId?: string }

export interface SecretosDeMiPin {
  pin: string
  passwordActual: string
}

/** `PIN_AUTORIZACION_PROPIO_DEFINIR`: al terminar se relee "PIN definido". */
export function useDefinirMiPin(leerSecretos: () => SecretosDeMiPin | null) {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesMiPin, void>(
    (_variables, operationId) => {
      const secretos = leerSecretos()
      if (secretos === null) return Promise.reject(new Error('No hay un PIN para enviar.'))
      return definirMiPin(secretos.pin, secretos.passwordActual, operationId)
    },
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesIdentidad.miPin() })
    },
  )
}
