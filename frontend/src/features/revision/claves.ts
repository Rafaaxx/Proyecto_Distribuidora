/**
 * Claves de consulta de TanStack Query de la revision (change 25). Resolver invalida la raiz: la bandeja, las
 * rechazadas y el resumen del aviso se leen de nuevo.
 */
export interface FiltrosDeObservaciones {
  estado?: 'PENDIENTE' | 'RESUELTA' | 'TODAS'
  codigo?: string
  tipo?: string
  usuarioId?: string
  jornadaId?: string
  /** Fecha `aaaa-mm-dd` (inclusive) sobre el momento de llegada. */
  desde?: string
  hasta?: string
}

export interface FiltrosDeRechazos {
  estado?: 'PENDIENTE' | 'RESUELTO' | 'TODOS'
  origen?: 'RECHAZO' | 'CUARENTENA'
  tipo?: string
  usuarioId?: string
  jornadaId?: string
}

export const clavesRevision = {
  raiz: () => ['revision'] as const,
  observaciones: (filtros: FiltrosDeObservaciones = {}) => ['revision', 'observaciones', filtros] as const,
  rechazos: (filtros: FiltrosDeRechazos = {}) => ['revision', 'rechazos', filtros] as const,
  resumen: () => ['revision', 'resumen'] as const,
}
