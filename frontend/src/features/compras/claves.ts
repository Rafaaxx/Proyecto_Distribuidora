/**
 * Claves de consulta de TanStack Query para compras y los catálogos de configuración que
 * consume su pantalla (change 11, tarea 11.1). Todas las de compras cuelgan de
 * `['compras', ...]`: al confirmar o anular se invalida esa raíz.
 */
export interface FiltrosCompras {
  proveedorId?: string
  estado?: 'CONFIRMADA' | 'ANULADA'
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
  numeroComprobante?: string
}

export const clavesCompras = {
  raiz: () => ['compras'] as const,
  listado: (filtros: FiltrosCompras = {}) => ['compras', 'listado', filtros] as const,
  detalle: (compraId: string) => ['compras', 'detalle', compraId] as const,
}

export const clavesConfiguracionDeCompras = {
  mediosPago: () => ['configuracion', 'medios-pago'] as const,
  motivos: (ambito: string) => ['configuracion', 'motivos', ambito] as const,
}
