/**
 * Claves de consulta de TanStack Query para `configuracion` (tarea 10.7),
 * mismo criterio que `features/catalogo/claves.ts`.
 */
export const clavesConfiguracion = {
  alicuotas: () => ['configuracion', 'alicuotas'] as const,
  fiscal: () => ['configuracion', 'fiscal'] as const,
  resumenReglaIva: () => ['costos', 'resumen-regla-iva'] as const,
}
