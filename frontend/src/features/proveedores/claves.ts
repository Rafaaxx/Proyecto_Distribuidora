/**
 * Claves de consulta de TanStack Query para proveedores y costos
 * informados (tarea 11.2, mismo criterio que `features/catalogo/claves.ts`).
 */
export interface FiltrosProveedores {
  texto?: string
  activo?: boolean
}

export const clavesProveedores = {
  proveedores: (filtros: FiltrosProveedores = {}) => ['proveedores', 'listado', filtros] as const,
  proveedor: (proveedorId: string) => ['proveedores', 'detalle', proveedorId] as const,
  opciones: () => ['proveedores', 'opciones'] as const,
  costoVigente: (productoId: string, fecha?: string) =>
    ['proveedores', 'costos', 'vigente', productoId, fecha ?? null] as const,
  historialDeCostos: (productoId: string) => ['proveedores', 'costos', 'historial', productoId] as const,
}
