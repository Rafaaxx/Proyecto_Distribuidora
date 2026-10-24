/**
 * Claves de consulta de TanStack Query para ventas (change 18a, tarea 12.2). Las ventas cuelgan
 * de `['ventas', ...]`: confirmar una venta invalida esa raíz y, además, el saldo del cliente, el
 * estado de cuenta, las cobranzas y el stock (la venta los mueve a todos).
 */
export interface FiltrosVentas {
  clienteId?: string
  usuarioId?: string
  jornadaId?: string
  ubicacionId?: string
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
}

/** Contexto de precio de la pantalla: cliente, lista o versión elegidas y ubicación (stock). */
export interface ContextoDePrecios {
  clienteId?: string
  listaId?: string
  versionId?: string
  ubicacionId?: string
}

export const clavesVentas = {
  raiz: () => ['ventas'] as const,
  listado: (filtros: FiltrosVentas = {}) => ['ventas', 'listado', filtros] as const,
  detalle: (ventaId: string) => ['ventas', 'detalle', ventaId] as const,
  precios: (contexto: ContextoDePrecios, texto: string) => ['ventas', 'precios', contexto, texto] as const,
  preciosDeProducto: (contexto: ContextoDePrecios, productoId: string) =>
    ['ventas', 'precios', 'producto', contexto, productoId] as const,
  numeracion: () => ['ventas', 'numeracion'] as const,
  versiones: (listaId: string) => ['ventas', 'versiones', listaId] as const,
  contexto: () => ['ventas', 'contexto'] as const,
  descuentosAplicables: () => ['ventas', 'descuentos-aplicables'] as const,
  credito: (clienteId: string) => ['ventas', 'credito', clienteId] as const,
}
