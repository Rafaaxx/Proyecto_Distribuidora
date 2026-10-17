/**
 * Claves de consulta de TanStack Query para cobranzas (change 17, tarea 14.1). Las cobranzas
 * cuelgan de `['cobranzas', ...]`; el saldo del cliente, de `['saldo-cliente', id]`, y el
 * selector de clientes, de `['clientes-opciones', texto]`: registrar o anular una cobranza
 * invalida las dos primeras raíces y la de cuentas corrientes (estado de cuenta).
 */
export interface FiltrosCobranzas {
  clienteId?: string
  estado?: 'CONFIRMADA' | 'ANULADA'
  usuarioId?: string
  jornadaId?: string
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
}

export const clavesCobranzas = {
  raiz: () => ['cobranzas'] as const,
  listado: (filtros: FiltrosCobranzas = {}) => ['cobranzas', 'listado', filtros] as const,
  detalle: (cobranzaId: string) => ['cobranzas', 'detalle', cobranzaId] as const,
}

export const clavesSaldoCliente = {
  raiz: () => ['saldo-cliente'] as const,
  cliente: (clienteId: string) => ['saldo-cliente', clienteId] as const,
}

export const clavesOpcionesDeClientes = {
  raiz: () => ['clientes-opciones'] as const,
  texto: (texto: string) => ['clientes-opciones', texto] as const,
}
