/**
 * Claves de consulta de TanStack Query para la sesión propia (tarea 6.2,
 * `design.md` D2-A). `['yo']` es la clave exacta que `usePermisos()`
 * consulta y que `AdminScreen` invalida o descarta en cada cambio de
 * token: no lleva el token ni ningún parámetro (D2, opción C descartada).
 */
export const clavesIdentidad = {
  yo: () => ['yo'] as const,
}
