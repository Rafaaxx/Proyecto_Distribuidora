/**
 * Claves de consulta de TanStack Query para descuentos (change 16, tarea 14.2). Todo cuelga de
 * `['descuentos', ...]`: el listado de reglas (con su filtro de estado), el detalle de cada una
 * y los roles con su tope. Invalidar `reglas()` arrastra todos los filtros del listado.
 */
export const clavesDescuentos = {
  raiz: () => ['descuentos'] as const,
  reglas: () => ['descuentos', 'reglas'] as const,
  listado: (estado: string | undefined) => ['descuentos', 'reglas', { estado: estado ?? null }] as const,
  detalle: (reglaId: string) => ['descuentos', 'regla', reglaId] as const,
  roles: () => ['descuentos', 'roles'] as const,
}
