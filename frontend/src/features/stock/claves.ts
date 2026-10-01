/**
 * Claves de consulta de TanStack Query para stock (change 09, tarea 8.1). Todas
 * cuelgan de `['stock', ...]`: al aceptarse un stock inicial o una modificación de
 * ubicación se invalida esa raíz, y con ella saldos, kardex y listados.
 * El costo promedio vive bajo `['costo-promedio', productoId]` (ruta de catalogo).
 */
export interface FiltrosKardex {
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
}

export const clavesStock = {
  raiz: () => ['stock'] as const,
  ubicaciones: (activo?: boolean) => ['stock', 'ubicaciones', { activo }] as const,
  saldos: (ubicacionId: string) => ['stock', 'saldos', ubicacionId] as const,
  kardex: (productoId: string, ubicacionId: string, filtros: FiltrosKardex = {}) =>
    ['stock', 'kardex', productoId, ubicacionId, filtros] as const,
}

export const clavesCostoPromedio = {
  raiz: () => ['costo-promedio'] as const,
  producto: (productoId: string) => ['costo-promedio', productoId] as const,
}
