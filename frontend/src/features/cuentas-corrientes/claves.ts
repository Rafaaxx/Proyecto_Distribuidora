import type { CuentaTipo } from '../../domain/cuentas-corrientes/presentacion'

/**
 * Claves de consulta de TanStack Query para cuentas corrientes (change 08,
 * grupo 7, tarea 7.1), mismo criterio que `features/clientes/claves.ts`.
 *
 * Todas cuelgan de `['cuentas-corrientes', cuentaTipo, entidadId]`: al
 * aceptarse un saldo inicial se invalida esa raíz y con ella el estado de
 * cuenta y el saldo de la ficha de esa entidad.
 */
export interface FiltrosEstadoDeCuenta {
  /** Fecha de negocio `aaaa-mm-dd` (TR-04), inclusive. */
  desde?: string
  hasta?: string
}

export const clavesCuentasCorrientes = {
  entidad: (cuentaTipo: CuentaTipo, entidadId: string) => ['cuentas-corrientes', cuentaTipo, entidadId] as const,
  estadoDeCuenta: (cuentaTipo: CuentaTipo, entidadId: string, filtros: FiltrosEstadoDeCuenta = {}) =>
    ['cuentas-corrientes', cuentaTipo, entidadId, 'estado', filtros] as const,
  saldo: (cuentaTipo: CuentaTipo, entidadId: string) =>
    ['cuentas-corrientes', cuentaTipo, entidadId, 'saldo'] as const,
}
