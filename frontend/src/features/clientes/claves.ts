/**
 * Claves de consulta de TanStack Query para clientes (change 07, grupo 5,
 * tarea 5.1), mismo criterio que `features/proveedores/claves.ts`.
 */
export interface FiltrosClientes {
  texto?: string
  estado?: string
  /** Change 20b (D15): solo los clientes de ese vendedor. */
  vendedorId?: string
  /** Change 20b (D15): solo los clientes sin vendedor asignado. */
  sinVendedor?: boolean
}

export const clavesClientes = {
  raiz: () => ['clientes'] as const,
  clientes: (filtros: FiltrosClientes = {}) => ['clientes', 'listado', filtros] as const,
  cliente: (clienteId: string) => ['clientes', 'detalle', clienteId] as const,
  vendedores: () => ['clientes', 'vendedores'] as const,
  consumidorFinal: () => ['clientes', 'consumidor-final'] as const,
}
