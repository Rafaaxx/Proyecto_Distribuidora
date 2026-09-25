import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import {
  listarHistorialDeCostos,
  listarOpcionesDeProveedores,
  listarProveedores,
  obtenerCostoVigente,
  obtenerProveedor,
} from './api'
import { clavesProveedores, type FiltrosProveedores } from './claves'

/**
 * Listados y consultas de proveedores y costos (tarea 11.2).
 * `useInfiniteQuery` para los paginados por cursor (mismo criterio que
 * `features/catalogo/useListados.ts`); `useQuery` para el detalle y el
 * costo vigente.
 */

export function useProveedores(filtros: FiltrosProveedores = {}) {
  return useInfiniteQuery({
    queryKey: clavesProveedores.proveedores(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarProveedores(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useProveedor(proveedorId: string | undefined) {
  return useQuery({
    queryKey: clavesProveedores.proveedor(proveedorId ?? ''),
    queryFn: () => obtenerProveedor(proveedorId as string),
    enabled: proveedorId !== undefined,
  })
}

/** Proveedores activos, sin CUIT ni contacto (`GET /proveedores/opciones`,
 * D8): usado por los selectores de la carga de costos y del formulario de
 * producto. */
export function useOpcionesDeProveedores() {
  return useInfiniteQuery({
    queryKey: clavesProveedores.opciones(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarOpcionesDeProveedores(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useCostoVigente(productoId: string | undefined, fecha?: string) {
  return useQuery({
    queryKey: clavesProveedores.costoVigente(productoId ?? '', fecha),
    queryFn: () => obtenerCostoVigente(productoId as string, fecha),
    enabled: productoId !== undefined,
  })
}

export function useHistorialDeCostos(productoId: string | undefined) {
  return useInfiniteQuery({
    queryKey: clavesProveedores.historialDeCostos(productoId ?? ''),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listarHistorialDeCostos(productoId as string, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
    enabled: productoId !== undefined,
  })
}
