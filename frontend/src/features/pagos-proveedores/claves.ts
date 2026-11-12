/**
 * Claves de consulta de TanStack Query para pagos a proveedores (change 12, tarea 8.2).
 * Las de pagos cuelgan de `['pagos-proveedores', ...]`; el saldo del proveedor, de
 * `['saldo-proveedor', id]`: registrar o anular un pago invalida ambas raíces y la de
 * cuentas corrientes (estado de cuenta).
 */
export interface FiltrosPagos {
  proveedorId?: string
  estado?: 'CONFIRMADA' | 'ANULADA'
  origen?: 'COMPRA' | 'INDEPENDIENTE'
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
}

export const clavesPagos = {
  raiz: () => ['pagos-proveedores'] as const,
  listado: (filtros: FiltrosPagos = {}) => ['pagos-proveedores', 'listado', filtros] as const,
  detalle: (pagoId: string) => ['pagos-proveedores', 'detalle', pagoId] as const,
}

export const clavesSaldoProveedor = {
  raiz: () => ['saldo-proveedor'] as const,
  proveedor: (proveedorId: string) => ['saldo-proveedor', proveedorId] as const,
}
