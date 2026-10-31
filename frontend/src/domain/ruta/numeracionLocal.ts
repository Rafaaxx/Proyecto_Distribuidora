import { formatearNumero } from '../ventas/numeracion'

/**
 * Número y secuencia que el teléfono asigna al confirmar una venta (change 22a, `design.md` D4;
 * VTA-06, `02` §7.7, SYN-03). Funciones puras: la lectura y la escritura de los contadores
 * ocurren dentro de la transacción de confirmación (`sync/confirmarVentaLocal.ts`).
 */
export interface DatosDeNumeracion {
  prefijo: string
  /** `numeracion.ultimo_correlativo` del bootstrap. */
  ultimoCorrelativoBootstrap: number
  /** `meta.ultimo_correlativo`: el último que usó este teléfono, o `null` si ninguno. */
  ultimoCorrelativoLocal: number | null
}

export interface NumeroAsignado {
  numero: string
  correlativo: number
}

/** `max(bootstrap, local) + 1` con el prefijo del dispositivo. */
export function siguienteNumeroLocal(datos: DatosDeNumeracion): NumeroAsignado {
  const correlativo = Math.max(datos.ultimoCorrelativoBootstrap, datos.ultimoCorrelativoLocal ?? 0) + 1
  return { numero: formatearNumero(datos.prefijo, correlativo), correlativo }
}

/** Secuencia estrictamente creciente de la cola del dispositivo; la primera es 1. */
export function siguienteSecuencia(ultima: number | null): number {
  return (ultima ?? 0) + 1
}
