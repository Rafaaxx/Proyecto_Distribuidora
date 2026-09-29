/**
 * Claves de consulta de TanStack Query para clientes (change 07, grupo 5,
 * tarea 5.1), mismo criterio que `features/proveedores/claves.ts`.
 */
export interface FiltrosClientes {
  texto?: string
  estado?: string
}

export const clavesClientes = {
  clientes: (filtros: FiltrosClientes = {}) => ['clientes', 'listado', filtros] as const,
  cliente: (clienteId: string) => ['clientes', 'detalle', clienteId] as const,
  consumidorFinal: () => ['clientes', 'consumidor-final'] as const,
}
