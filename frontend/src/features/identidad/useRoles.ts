import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import { clavesDescuentos } from '../descuentos/claves'
import { clavesIdentidad } from './claves'
import {
  cambiarPermisosDeRol,
  crearRol,
  darDeBajaRol,
  listarCatalogoDePermisos,
  listarRolesConPermisos,
  reactivarRol,
  renombrarRol,
  type RolCambiado,
} from './rolesApi'

/** Lecturas y escritura de "Roles y permisos" (change 17b, D9; change 20b, D10 y D11). TanStack Query solo en `/admin`. */

export function useRolesConPermisos(habilitado = true) {
  return useQuery({ queryKey: clavesIdentidad.roles(), queryFn: listarRolesConPermisos, enabled: habilitado })
}

export function useCatalogoDePermisos(habilitado = true) {
  return useQuery({ queryKey: clavesIdentidad.permisos(), queryFn: listarCatalogoDePermisos, enabled: habilitado })
}

type VariablesCambio = { rolId: string; permisos: string[]; operationId?: string }

/**
 * `ROL_PERMISOS_CAMBIAR`. Al guardar se invalida `['yo']` para que el menú propio se actualice si
 * se tocó el propio rol (ADR-017, ADR-027), la lista de roles y la de "Topes por rol", que muestra
 * los permisos del rol.
 */
export function useCambiarPermisosDeRol() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesCambio, unknown>(
    ({ rolId, permisos }, operationId) => cambiarPermisosDeRol(rolId, permisos, operationId),
    () => {
      void queryClient.invalidateQueries({ queryKey: clavesIdentidad.yo() })
      void queryClient.invalidateQueries({ queryKey: clavesIdentidad.roles() })
      void queryClient.invalidateQueries({ queryKey: clavesDescuentos.roles() })
    },
  )
}

/**
 * Tras crear, renombrar, dar de baja o reactivar un rol se relee la lista de roles, la de "Topes
 * por rol", los usuarios (nombre y estado del rol) y la sesión propia, por si se tocó el rol
 * propio (ADR-027).
 */
function useInvalidarTrasCambiarRol() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesIdentidad.roles() })
    void queryClient.invalidateQueries({ queryKey: clavesDescuentos.roles() })
    void queryClient.invalidateQueries({ queryKey: clavesIdentidad.usuarios() })
    void queryClient.invalidateQueries({ queryKey: clavesIdentidad.yo() })
  }
}

type ConOperationId = { operationId?: string }

export function useCrearRol() {
  const invalidar = useInvalidarTrasCambiarRol()
  return useMutacionConOperationId<{ nombre: string; permisos: string[] } & ConOperationId, RolCambiado>(
    ({ nombre, permisos }, operationId) => crearRol(nombre, permisos, operationId),
    invalidar,
  )
}

export function useRenombrarRol() {
  const invalidar = useInvalidarTrasCambiarRol()
  return useMutacionConOperationId<{ rolId: string; nombre: string } & ConOperationId, RolCambiado>(
    ({ rolId, nombre }, operationId) => renombrarRol(rolId, nombre, operationId),
    invalidar,
  )
}

export function useDarDeBajaRol() {
  const invalidar = useInvalidarTrasCambiarRol()
  return useMutacionConOperationId<{ rolId: string } & ConOperationId, RolCambiado>(
    ({ rolId }, operationId) => darDeBajaRol(rolId, operationId),
    invalidar,
  )
}

export function useReactivarRol() {
  const invalidar = useInvalidarTrasCambiarRol()
  return useMutacionConOperationId<{ rolId: string } & ConOperationId, RolCambiado>(
    ({ rolId }, operationId) => reactivarRol(rolId, operationId),
    invalidar,
  )
}
