import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  activarReglaDescuento,
  crearReglaDescuento,
  definirTopeDeRol,
  listarReglasDescuento,
  listarRolesConTope,
  modificarReglaDescuento,
  obtenerReglaDescuento,
  pausarReglaDescuento,
  type ReglaDescuento,
  type ReglaDescuentoCrearDatos,
  type ReglaDescuentoModificarDatos,
  type RolConTope,
  type TopeDeRolDatos,
} from './api'
import { clavesDescuentos } from './claves'

/**
 * Lecturas y escrituras de reglas de descuento y de topes por rol (change 16, tarea 14.2).
 * TanStack Query solo en `/admin` (`CLAUDE.md` §2). Mismo mecanismo de `Operation-Id` que compras y
 * precios (`useMutacionConOperationId`): se genera una vez por envío y el reintento automático ante
 * un error de RED reenvía exactamente el mismo valor (INV-06); un rechazo de dominio no se
 * reintenta. Las pantallas que quieren que el reintento MANUAL del mismo contenido reenvíe la misma
 * operación pasan `operationId` (`useOperationIdDeEnvio`). Todas las escrituras son `ONLINE` puras:
 * no se encola nada sin conexión.
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

// --- lecturas ----------------------------------------------------------------------------

/** Las reglas de la organización, de la más nueva a la más vieja; `estado` admite `VENCIDA`. */
export function useReglasDescuento(estado: string | undefined) {
  return useInfiniteQuery({
    queryKey: clavesDescuentos.listado(estado),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarReglasDescuento(estado, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.siguiente_cursor ?? undefined,
  })
}

export function useReglaDescuento(reglaId: string | undefined) {
  return useQuery({
    queryKey: clavesDescuentos.detalle(reglaId ?? ''),
    queryFn: () => obtenerReglaDescuento(reglaId as string),
    enabled: reglaId !== undefined,
  })
}

/** Los roles de la organización con su tope de descuento manual (`ADMIN_USUARIOS`). */
export function useRolesConTope() {
  return useQuery({ queryKey: clavesDescuentos.roles(), queryFn: listarRolesConTope })
}

// --- escrituras --------------------------------------------------------------------------

type ConOperationId = { operationId?: string }

function useInvalidadores() {
  const queryClient = useQueryClient()
  const invalidar = (clave: readonly unknown[]) => {
    void queryClient.invalidateQueries({ queryKey: clave })
  }
  return {
    listado: () => invalidar(clavesDescuentos.reglas()),
    regla: (reglaId: string) => invalidar(clavesDescuentos.detalle(reglaId)),
    roles: () => invalidar(clavesDescuentos.roles()),
  }
}

type VariablesCrear = ReglaDescuentoCrearDatos & ConOperationId

export function useCrearReglaDescuento() {
  const { listado } = useInvalidadores()
  return useMutacionConOperationId<VariablesCrear, ReglaDescuento>(({ operationId: _id, ...datos }, operationId) => {
    void _id
    return crearReglaDescuento(datos, operationId)
  }, listado)
}

type VariablesModificar = ReglaDescuentoModificarDatos & { reglaId: string } & ConOperationId

export function useModificarReglaDescuento() {
  const { listado, regla } = useInvalidadores()
  return useMutacionConOperationId<VariablesModificar, ReglaDescuento>(
    ({ reglaId, operationId: _id, ...datos }, operationId) => {
      void _id
      return modificarReglaDescuento(reglaId, datos, operationId)
    },
    (_resultado, variables) => {
      listado()
      regla(variables.reglaId)
    },
  )
}

type VariablesDeEstado = { reglaId: string } & ConOperationId

export function useActivarReglaDescuento() {
  const { listado, regla } = useInvalidadores()
  return useMutacionConOperationId<VariablesDeEstado, ReglaDescuento>(
    ({ reglaId }, operationId) => activarReglaDescuento(reglaId, operationId),
    (_resultado, variables) => {
      listado()
      regla(variables.reglaId)
    },
  )
}

export function usePausarReglaDescuento() {
  const { listado, regla } = useInvalidadores()
  return useMutacionConOperationId<VariablesDeEstado, ReglaDescuento>(
    ({ reglaId }, operationId) => pausarReglaDescuento(reglaId, operationId),
    (_resultado, variables) => {
      listado()
      regla(variables.reglaId)
    },
  )
}

type VariablesTope = TopeDeRolDatos & { rolId: string } & ConOperationId

/** Define el tope de descuento manual de un rol (`ROL_TOPE_DESCUENTO_DEFINIR`, `ADMIN_USUARIOS`). */
export function useDefinirTopeDeRol() {
  const { roles } = useInvalidadores()
  return useMutacionConOperationId<VariablesTope, RolConTope>(
    ({ rolId, operationId: _id, ...datos }, operationId) => {
      void _id
      return definirTopeDeRol(rolId, datos, operationId)
    },
    roles,
  )
}
