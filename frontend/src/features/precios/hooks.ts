import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'

import { useMutacionConOperationId } from '../compras/hooks'
import {
  anularVersion,
  crearLista,
  crearRegla,
  definirListaPredeterminada,
  definirRedondeoDeCategoria,
  fijarPrecioManual,
  generarBorrador,
  listarListas,
  listarOpcionesDeListas,
  listarPreciosDeVersion,
  listarReglas,
  listarVersiones,
  modificarLista,
  modificarRegla,
  obtenerBorrador,
  obtenerLista,
  obtenerListaPredeterminada,
  publicarVersion,
  type Generacion,
  type Lista,
  type ListaCrearDatos,
  type ListaModificarDatos,
  type ListaPredeterminada,
  type ListaPredeterminadaDatos,
  type PrecioFijado,
  type PublicarDatos,
  type RedondeoCategoria,
  type RedondeoCategoriaDatos,
  type Regla,
  type ReglaCrearDatos,
  type ReglaModificarDatos,
  type Version,
} from './api'
import { clavesPrecios } from './claves'

/**
 * Lecturas y escrituras de listas de precios (change 13, tarea 12.2). TanStack Query solo en
 * `/admin` (`CLAUDE.md` §2). Mismo mecanismo de `Operation-Id` que compras
 * (`useMutacionConOperationId`): se genera una vez por envío y el reintento automático ante
 * un error de RED reenvía exactamente el mismo valor (INV-06); un rechazo de dominio no se
 * reintenta. Las pantallas que quieren que el reintento MANUAL del mismo contenido reenvíe la
 * misma operación pasan `operationId` (`useOperationIdPorContenido`). Todas las escrituras de
 * precios son `ONLINE` puras: no se encola nada sin conexión.
 */

export { esErrorDeRed } from '../../lib/api/reintentoDeRed'

// --- lecturas ----------------------------------------------------------------------------

export function useListas() {
  return useQuery({ queryKey: clavesPrecios.listado(), queryFn: listarListas })
}

/** Las listas activas (id y nombre) para los selectores de la ficha del cliente y de configuración. */
export function useOpcionesDeListas(habilitado = true) {
  return useQuery({ queryKey: clavesPrecios.opciones(), queryFn: listarOpcionesDeListas, enabled: habilitado })
}

export function useListaDetalle(listaId: string | undefined) {
  return useQuery({
    queryKey: clavesPrecios.detalle(listaId ?? ''),
    queryFn: () => obtenerLista(listaId as string),
    enabled: listaId !== undefined,
  })
}

export function useReglas(listaId: string | undefined) {
  return useQuery({
    queryKey: clavesPrecios.reglas(listaId ?? ''),
    queryFn: () => listarReglas(listaId as string),
    enabled: listaId !== undefined,
  })
}

/** El borrador de la lista, página a página (`siguiente_cursor`). Sin borrador responde 404. */
export function useBorrador(listaId: string | undefined) {
  return useInfiniteQuery({
    queryKey: clavesPrecios.borrador(listaId ?? ''),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => obtenerBorrador(listaId as string, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.siguiente_cursor ?? undefined,
    enabled: listaId !== undefined,
    retry: false,
  })
}

export function useVersiones(listaId: string | undefined) {
  return useQuery({
    queryKey: clavesPrecios.versiones(listaId ?? ''),
    queryFn: () => listarVersiones(listaId as string),
    enabled: listaId !== undefined,
  })
}

export function usePreciosDeVersion(listaId: string | undefined, versionId: string | undefined) {
  return useInfiniteQuery({
    queryKey: clavesPrecios.preciosDeVersion(listaId ?? '', versionId ?? ''),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listarPreciosDeVersion(listaId as string, versionId as string, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.siguiente_cursor ?? undefined,
    enabled: listaId !== undefined && versionId !== undefined,
  })
}

export function useListaPredeterminada() {
  return useQuery({ queryKey: clavesPrecios.predeterminada(), queryFn: obtenerListaPredeterminada })
}

// --- escrituras --------------------------------------------------------------------------

type ConOperationId = { operationId?: string }

function useInvalidadores() {
  const queryClient = useQueryClient()
  const invalidar = (clave: readonly unknown[]) => {
    void queryClient.invalidateQueries({ queryKey: clave })
  }
  return {
    listado: () => {
      invalidar(clavesPrecios.listado())
      invalidar(clavesPrecios.opciones())
    },
    lista: (listaId: string) => invalidar(clavesPrecios.detalle(listaId)),
    reglas: (listaId: string) => invalidar(clavesPrecios.reglas(listaId)),
    borradorYVersiones: (listaId: string) => {
      invalidar(clavesPrecios.borrador(listaId))
      invalidar(clavesPrecios.versiones(listaId))
      invalidar(clavesPrecios.listado())
    },
    predeterminada: () => invalidar(clavesPrecios.predeterminada()),
  }
}

type VariablesCrearLista = ListaCrearDatos & ConOperationId

export function useCrearLista() {
  const { listado } = useInvalidadores()
  return useMutacionConOperationId<VariablesCrearLista, Lista>(({ operationId: _id, ...datos }, operationId) => {
    void _id
    return crearLista(datos, operationId)
  }, listado)
}

type VariablesModificarLista = ListaModificarDatos & { listaId: string } & ConOperationId

export function useModificarLista() {
  const { listado, lista } = useInvalidadores()
  return useMutacionConOperationId<VariablesModificarLista, Lista>(
    ({ listaId, operationId: _id, ...datos }, operationId) => {
      void _id
      return modificarLista(listaId, datos, operationId)
    },
    (_resultado, variables) => {
      listado()
      lista(variables.listaId)
    },
  )
}

type VariablesCrearRegla = ReglaCrearDatos & { listaId: string } & ConOperationId

export function useCrearRegla() {
  const { reglas, lista } = useInvalidadores()
  return useMutacionConOperationId<VariablesCrearRegla, Regla>(
    ({ listaId, operationId: _id, ...datos }, operationId) => {
      void _id
      return crearRegla(listaId, datos, operationId)
    },
    (_resultado, variables) => {
      reglas(variables.listaId)
      lista(variables.listaId)
    },
  )
}

type VariablesModificarRegla = ReglaModificarDatos & { listaId: string; reglaId: string } & ConOperationId

export function useModificarRegla() {
  const { reglas, lista } = useInvalidadores()
  return useMutacionConOperationId<VariablesModificarRegla, Regla>(
    ({ listaId, reglaId, operationId: _id, ...datos }, operationId) => {
      void _id
      return modificarRegla(listaId, reglaId, datos, operationId)
    },
    (_resultado, variables) => {
      reglas(variables.listaId)
      lista(variables.listaId)
    },
  )
}

type VariablesRedondeoCategoria = RedondeoCategoriaDatos & { listaId: string; categoriaId: string } & ConOperationId

export function useDefinirRedondeoDeCategoria() {
  const { lista } = useInvalidadores()
  return useMutacionConOperationId<VariablesRedondeoCategoria, RedondeoCategoria>(
    ({ listaId, categoriaId, operationId: _id, ...datos }, operationId) => {
      void _id
      return definirRedondeoDeCategoria(listaId, categoriaId, datos, operationId)
    },
    (_resultado, variables) => lista(variables.listaId),
  )
}

/** Generar o regenerar el borrador (D5): refresca el borrador, las versiones y el listado. */
export function useGenerarBorrador() {
  const { borradorYVersiones } = useInvalidadores()
  return useMutacionConOperationId<{ listaId: string } & ConOperationId, Generacion>(
    ({ listaId }, operationId) => generarBorrador(listaId, operationId),
    (_resultado, variables) => borradorYVersiones(variables.listaId),
  )
}

type VariablesFijarPrecio = { listaId: string; versionId: string; productoId: string; precio_final: string | null } & ConOperationId

export function useFijarPrecioManual() {
  const { borradorYVersiones } = useInvalidadores()
  return useMutacionConOperationId<VariablesFijarPrecio, PrecioFijado>(
    ({ listaId, versionId, productoId, precio_final }, operationId) =>
      fijarPrecioManual(listaId, versionId, productoId, precio_final, operationId),
    (_resultado, variables) => borradorYVersiones(variables.listaId),
  )
}

type VariablesPublicar = PublicarDatos & { listaId: string; versionId: string } & ConOperationId

export function usePublicarVersion() {
  const { borradorYVersiones } = useInvalidadores()
  return useMutacionConOperationId<VariablesPublicar, Version>(
    ({ listaId, versionId, vigencia_desde, vigencia_hasta }, operationId) =>
      publicarVersion(listaId, versionId, { vigencia_desde, vigencia_hasta }, operationId),
    (_resultado, variables) => borradorYVersiones(variables.listaId),
  )
}

export function useAnularVersion() {
  const { borradorYVersiones } = useInvalidadores()
  return useMutacionConOperationId<{ listaId: string; versionId: string } & ConOperationId, Version>(
    ({ listaId, versionId }, operationId) => anularVersion(listaId, versionId, operationId),
    (_resultado, variables) => borradorYVersiones(variables.listaId),
  )
}

export function useDefinirListaPredeterminada() {
  const { predeterminada, listado } = useInvalidadores()
  return useMutacionConOperationId<ListaPredeterminadaDatos & ConOperationId, ListaPredeterminada>(
    ({ lista_id }, operationId) => definirListaPredeterminada({ lista_id }, operationId),
    () => {
      predeterminada()
      listado()
    },
  )
}
