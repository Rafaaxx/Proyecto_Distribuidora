import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { listarCategorias, listarMarcas, listarProductos, obtenerProducto } from './api'
import { clavesCatalogo, type FiltrosProductos } from './claves'

/**
 * Listados paginados de catálogo (tarea 10.2). `useInfiniteQuery` porque
 * la pantalla de listado (tarea 10.4) pide "cargar más": cada página trae
 * su `cursor_siguiente` (`03`/`design.md` D-cursor), `null` cuando no hay
 * más.
 */

export function useCategorias() {
  return useInfiniteQuery({
    queryKey: clavesCatalogo.categorias(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarCategorias(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useMarcas() {
  return useInfiniteQuery({
    queryKey: clavesCatalogo.marcas(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarMarcas(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useProductos(filtros: FiltrosProductos = {}) {
  return useInfiniteQuery({
    queryKey: clavesCatalogo.productos(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarProductos(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useProducto(productoId: string | undefined) {
  return useQuery({
    queryKey: clavesCatalogo.producto(productoId ?? ''),
    queryFn: () => obtenerProducto(productoId as string),
    enabled: productoId !== undefined,
  })
}
