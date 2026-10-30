import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import { clavesClientes } from '../clientes/claves'
import { clavesIdentidad } from './claves'
import {
  cambiarMiContrasena,
  cambiarRolDeUsuario,
  crearUsuario,
  darDeBajaUsuario,
  definirTopeDeUsuario,
  desbloquearUsuario,
  listarUsuariosDetalle,
  modificarUsuario,
  obtenerUsuario,
  reactivarUsuario,
  restablecerContrasenaDeUsuario,
  type DatosDeAltaParaApi,
  type FiltrosDeUsuarios,
  type UsuarioCambiado,
  type UsuarioCreado,
} from './usuariosApi'

/**
 * Lecturas y escrituras de "Usuarios" y "Mi contraseña" (change 20b, D1, D16, D20). TanStack
 * Query solo en `/admin`. Los secretos (contraseñas) NO viajan en las variables de la mutación
 * -que TanStack Query conserva en memoria- ni entran a la caché: los entrega una referencia
 * (`useSecretoEfimero`, `usePin.ts`) que quien llama llena justo antes de enviar y vacía al
 * terminar. El `Operation-Id` lo conserva quien llama: un reintento con los datos corregidos usa
 * el mismo (un rechazo no deja fila de comando).
 */

export function useUsuariosDetalle(filtros: FiltrosDeUsuarios = {}, habilitado = true) {
  return useQuery({
    queryKey: clavesIdentidad.usuariosDetalle(filtros),
    queryFn: () => listarUsuariosDetalle(filtros),
    enabled: habilitado,
  })
}

export function useUsuario(usuarioId: string | undefined) {
  return useQuery({
    queryKey: clavesIdentidad.usuario(usuarioId ?? ''),
    queryFn: () => obtenerUsuario(usuarioId as string),
    enabled: usuarioId !== undefined,
  })
}

/**
 * Tras cualquier cambio de un usuario se relee el listado, la ficha, los roles (conteos) y, por
 * si se tocó algo propio, `['yo']` (ADR-027). Los clientes asignados también se releen: una baja
 * no los toca pero la ficha los muestra.
 */
function useInvalidarTrasCambiarUsuario() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesIdentidad.usuarios() })
    void queryClient.invalidateQueries({ queryKey: clavesIdentidad.roles() })
    void queryClient.invalidateQueries({ queryKey: clavesIdentidad.yo() })
    void queryClient.invalidateQueries({ queryKey: clavesClientes.raiz() })
  }
}

type ConOperationId = { operationId?: string }

/** `USUARIO_CREAR`; la contraseña viaja en `datos` solo mientras dura la llamada. */
export function useCrearUsuario(leerDatos: () => DatosDeAltaParaApi | null) {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<ConOperationId, UsuarioCreado>(
    (_variables, operationId) => {
      const datos = leerDatos()
      if (datos === null) return Promise.reject(new Error('No hay datos para enviar.'))
      return crearUsuario(datos, operationId)
    },
    invalidar,
  )
}

export function useModificarUsuario() {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<
    { usuarioId: string; nombre: string; email: string | null } & ConOperationId,
    UsuarioCambiado
  >(({ usuarioId, nombre, email }, operationId) => modificarUsuario(usuarioId, { nombre, email }, operationId), invalidar)
}

export function useDarDeBajaUsuario() {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<{ usuarioId: string; observacion: string | null } & ConOperationId, UsuarioCambiado>(
    ({ usuarioId, observacion }, operationId) => darDeBajaUsuario(usuarioId, observacion, operationId),
    invalidar,
  )
}

export function useReactivarUsuario() {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<{ usuarioId: string } & ConOperationId, UsuarioCambiado>(
    ({ usuarioId }, operationId) => reactivarUsuario(usuarioId, operationId),
    invalidar,
  )
}

export function useCambiarRolDeUsuario() {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<{ usuarioId: string; rolId: string } & ConOperationId, UsuarioCambiado>(
    ({ usuarioId, rolId }, operationId) => cambiarRolDeUsuario(usuarioId, rolId, operationId),
    invalidar,
  )
}

export function useDefinirTopeDeUsuario() {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<
    { usuarioId: string; topeDescuento: string | null } & ConOperationId,
    UsuarioCambiado
  >(
    ({ usuarioId, topeDescuento }, operationId) => definirTopeDeUsuario(usuarioId, topeDescuento, operationId),
    invalidar,
  )
}

/** `USUARIO_CONTRASENA_RESTABLECER`: la contraseña viene de la referencia efímera. */
export function useRestablecerContrasena(leerContrasena: () => string | null) {
  const invalidar = useInvalidarTrasCambiarUsuario()
  return useMutacionConOperationId<{ usuarioId: string } & ConOperationId, void>(
    ({ usuarioId }, operationId) => {
      const contrasena = leerContrasena()
      if (contrasena === null) return Promise.reject(new Error('No hay una contraseña para enviar.'))
      return restablecerContrasenaDeUsuario(usuarioId, contrasena, operationId)
    },
    invalidar,
  )
}

export interface SecretosDeMiContrasena {
  actual: string
  nueva: string
}

/** `CONTRASENA_PROPIA_CAMBIAR`: las dos contraseñas vienen de la referencia efímera (D20). */
export function useCambiarMiContrasena(leerSecretos: () => SecretosDeMiContrasena | null) {
  return useMutacionConOperationId<ConOperationId, void>((_variables, operationId) => {
    const secretos = leerSecretos()
    if (secretos === null) return Promise.reject(new Error('No hay contraseñas para enviar.'))
    return cambiarMiContrasena(secretos.actual, secretos.nueva, operationId)
  }, () => undefined)
}

/** `USUARIO_DESBLOQUEAR` (ADR-057). */
export function useDesbloquearUsuario() {
  return useMutacionConOperationId<{ usuarioId: string } & ConOperationId, void>(
    ({ usuarioId }, operationId) => desbloquearUsuario(usuarioId, operationId),
    () => undefined,
  )
}
