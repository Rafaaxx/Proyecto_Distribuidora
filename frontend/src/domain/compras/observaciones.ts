/**
 * Texto para el usuario de las observaciones que deja `COMPRA_ANULAR` (SYN-04/SYN-07,
 * CMP-06, CMP-07). Un código que esta lista no conoce se muestra tal cual: nunca se
 * esconde una observación del servidor.
 */
const AVISOS: Readonly<Record<string, string>> = {
  ANULACION_COMPRA_SIN_RECALCULO:
    'La compra se anuló, pero el costo promedio no se recalculó.',
  STOCK_NEGATIVO: 'La anulación dejó stock negativo en al menos un producto.',
}

export function avisoDeObservacion(codigo: string): string {
  return AVISOS[codigo] ?? `Observación del servidor: ${codigo}.`
}
