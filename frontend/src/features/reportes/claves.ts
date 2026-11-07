/**
 * Claves de consulta de TanStack Query de los reportes (change 26). Los reportes son de solo lectura: no hay
 * invalidación por escritura, cada filtro es una clave distinta.
 */
export interface FiltrosDeVentas {
  /** Fecha de negocio `aaaa-mm-dd` (inclusive). Sin ella el servidor usa el mes en curso (D1). */
  desde?: string
  hasta?: string
  vendedorId?: string
  /** Página de cada lista paginada (D14); desde 1, y sin ella el servidor trae la primera. */
  paginaPorDia?: number
  paginaPorProducto?: number
  paginaAnuladas?: number
}

/** El período de los reportes de observaciones y ajustes (D9, D10). */
export interface FiltrosDePeriodo {
  desde?: string
  hasta?: string
}

export type EstadoDeJornadaFiltro = 'ABIERTA' | 'EN_RENDICION' | 'CERRADA' | 'LIBERADA'

export interface FiltrosDeRendiciones extends FiltrosDePeriodo {
  vendedorId?: string
  estado?: EstadoDeJornadaFiltro
  /** Página de la lista de jornadas (D14). */
  pagina?: number
}

export type FiltroDeSaldo = 'DEUDORES' | 'A_FAVOR' | 'CON_SALDO' | 'TODOS'

export interface FiltrosDeSaldosDeClientes {
  /** Sin él el servidor usa `CON_SALDO` (D8). */
  saldo?: FiltroDeSaldo
  vendedorId?: string
  estado?: 'ACTIVO' | 'SUSPENDIDO' | 'INACTIVO'
  texto?: string
  pagina?: number
}

export interface FiltrosDeSaldosDeProveedores {
  saldo?: FiltroDeSaldo
  estado?: 'ACTIVO' | 'INACTIVO'
  texto?: string
  pagina?: number
}

export const clavesReportes = {
  raiz: () => ['reportes'] as const,
  ventas: (filtros: FiltrosDeVentas = {}) => ['reportes', 'ventas', filtros] as const,
  rendiciones: (filtros: FiltrosDeRendiciones = {}) => ['reportes', 'rendiciones', filtros] as const,
  detalleDeRendicion: (jornadaId: string) => ['reportes', 'rendiciones', 'detalle', jornadaId] as const,
  observaciones: (filtros: FiltrosDePeriodo = {}) => ['reportes', 'observaciones', filtros] as const,
  ajustes: (filtros: FiltrosDePeriodo = {}) => ['reportes', 'ajustes', filtros] as const,
  saldosDeClientes: (filtros: FiltrosDeSaldosDeClientes = {}) => ['reportes', 'saldos', 'clientes', filtros] as const,
  saldosDeProveedores: (filtros: FiltrosDeSaldosDeProveedores = {}) =>
    ['reportes', 'saldos', 'proveedores', filtros] as const,
}
