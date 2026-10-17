import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import { clavesDescuentos } from '../descuentos/claves'
import { clavesIdentidad } from './claves'
import { cambiarPermisosDeRol, listarCatalogoDePermisos, listarRolesConPermisos } from './rolesApi'

/** Lecturas y escritura de "Roles y permisos" (change 17b, D9). TanStack Query solo en `/admin`. */

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
