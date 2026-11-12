import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

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

/**
 * Productos activos de un proveedor (filtro `proveedor_id` del servidor, change 11, D17),
 * recorriendo todas las páginas: los selectores de la carga de costos y del formulario de
 * compra necesitan la lista completa, no la primera página. Sin `proveedorId` no pide nada.
 */
export function useProductosDelProveedor(proveedorId: string | undefined) {
  const consulta = useInfiniteQuery({
    queryKey: clavesCatalogo.productos({ activo: true, proveedorId }),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listarProductos({ activo: true, proveedorId }, pageParam, 100),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
    enabled: proveedorId !== undefined && proveedorId !== '',
  })
  const { hasNextPage, isFetching, fetchNextPage } = consulta
  // Páginas ya cargadas: entra en las dependencias para que el efecto vuelva a correr tras
  // cada página aunque `hasNextPage` e `isFetching` terminen en el mismo valor.
  const paginasCargadas = consulta.data?.pages.length ?? 0
  useEffect(() => {
    if (hasNextPage && !isFetching) void fetchNextPage()
  }, [hasNextPage, isFetching, fetchNextPage, paginasCargadas])

  return {
    productos: consulta.data?.pages.flatMap((pagina) => pagina.items) ?? [],
    cargando: consulta.isFetching || hasNextPage,
    error: consulta.error,
  }
}

/** Detalle (con presentaciones) de varios productos a la vez, uno por línea de un formulario.
 * Comparte la caché de `useProducto`; los ids vacíos no piden nada. */
export function useDetallesDeProductos(productoIds: readonly string[]) {
  return useQueries({
    queries: productoIds.map((productoId) => ({
      queryKey: clavesCatalogo.producto(productoId),
      queryFn: () => obtenerProducto(productoId),
      enabled: productoId !== '',
    })),
  })
}
