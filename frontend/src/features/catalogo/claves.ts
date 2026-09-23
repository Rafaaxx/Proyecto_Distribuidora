/**
 * Claves de consulta de TanStack Query para catálogo (tarea 10.2). Los
 * listados llevan sus filtros en la clave (invalida solo lo que cambió); el
 * detalle de producto lleva el id.
 */
export interface FiltrosProductos {
  texto?: string
  categoriaId?: string
  marcaId?: string
  activo?: boolean
}

export const clavesCatalogo = {
  categorias: () => ['catalogo', 'categorias'] as const,
  marcas: () => ['catalogo', 'marcas'] as const,
  productos: (filtros: FiltrosProductos = {}) => ['catalogo', 'productos', filtros] as const,
  producto: (productoId: string) => ['catalogo', 'productos', 'detalle', productoId] as const,
}
