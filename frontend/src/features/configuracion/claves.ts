/**
 * Claves de consulta de TanStack Query para `configuracion` (tarea 10.7),
 * mismo criterio que `features/catalogo/claves.ts`.
 */
export const clavesConfiguracion = {
  alicuotas: () => ['configuracion', 'alicuotas'] as const,
  fiscal: () => ['configuracion', 'fiscal'] as const,
  /** Medios activos y administración cuelgan de la misma raíz: invalidarla refresca ambas. */
  mediosPagoRaiz: () => ['configuracion', 'medios-pago'] as const,
  mediosPagoAdmin: () => ['configuracion', 'medios-pago', 'todos'] as const,
  resumenReglaIva: () => ['costos', 'resumen-regla-iva'] as const,
}
