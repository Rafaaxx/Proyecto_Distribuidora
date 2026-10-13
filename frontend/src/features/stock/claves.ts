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

export interface FiltrosTransferencias {
  ubicacionId?: string
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
}

export interface FiltrosAjustes extends FiltrosTransferencias {
  motivoId?: string
}

export interface FiltrosJornadas {
  ubicacionId?: string
  usuarioId?: string
  estado?: string
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
  transferencias: (filtros: FiltrosTransferencias = {}) => ['stock', 'transferencias', 'listado', filtros] as const,
  transferencia: (id: string) => ['stock', 'transferencias', 'detalle', id] as const,
  ajustes: (filtros: FiltrosAjustes = {}) => ['stock', 'ajustes', 'listado', filtros] as const,
  ajuste: (id: string) => ['stock', 'ajustes', 'detalle', id] as const,
  jornadas: (filtros: FiltrosJornadas = {}) => ['stock', 'jornadas', 'listado', filtros] as const,
  jornada: (id: string) => ['stock', 'jornadas', 'detalle', id] as const,
  jornadaActual: () => ['stock', 'jornadas', 'actual'] as const,
}

export const clavesCostoPromedio = {
  raiz: () => ['costo-promedio'] as const,
  producto: (productoId: string) => ['costo-promedio', productoId] as const,
}
