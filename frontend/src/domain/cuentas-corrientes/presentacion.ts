import { formatearImporte, parsearImporteDesdeApi } from '../../lib/money'

/**
 * Presentación de la cuenta corriente (change 08, tareas 7.2 y 7.3): rótulos
 * de negocio del saldo y del sentido de un movimiento, y formato de los
 * importes. Lógica pura, sin React: las pantallas solo la llaman.
 *
 * Convención de signo (CC-04, `01` §2): un saldo positivo es lo que el
 * cliente nos debe (o lo que le debemos al proveedor); uno negativo es un
 * saldo a favor de la contraparte. Todos los importes llegan como string de
 * la API y se formatean con `lib/money.ts`, sin pasar nunca por `number`
 * (INV-03).
 */
export type CuentaTipo = 'CLIENTE' | 'PROVEEDOR'
export type Sentido = 'AUMENTA' | 'REDUCE'

const ROTULOS_DE_SALDO: Record<CuentaTipo, { deuda: string; aFavor: string }> = {
  CLIENTE: { deuda: 'Nos debe', aFavor: 'Saldo a favor' },
  PROVEEDOR: { deuda: 'Le debemos', aFavor: 'Saldo a nuestro favor' },
}

const ETIQUETAS_DE_SENTIDO: Record<CuentaTipo, Record<Sentido, string>> = {
  CLIENTE: { AUMENTA: 'Nos debe', REDUCE: 'Saldo a favor del cliente' },
  PROVEEDOR: { AUMENTA: 'Le debemos', REDUCE: 'Saldo a favor nuestro' },
}

const ETIQUETAS_DE_TIPO: Record<string, string> = {
  SALDO_INICIAL: 'Saldo inicial',
  VENTA: 'Venta',
  ANULACION_VENTA: 'Anulación de venta',
  COBRANZA: 'Cobranza',
  ANULACION_COBRANZA: 'Anulación de cobranza',
  COMPRA: 'Compra',
  ANULACION_COMPRA: 'Anulación de compra',
  PAGO: 'Pago',
  ANULACION_PAGO: 'Anulación de pago',
}

/** `"$ 150.000,00"`; un negativo conserva su signo (`"$ -3.000,00"`). */
export function formatearMonto(valorApi: string): string {
  return `$ ${formatearImporte(parsearImporteDesdeApi(valorApi))}`
}

/** Saldo con su rótulo según el signo y la cuenta: `"Nos debe $ 150.000,00"`,
 * `"Saldo a favor $ 2.500,50"`, `"Saldo $ 0,00"`. */
export function textoDeSaldo(cuentaTipo: CuentaTipo, saldoApi: string): string {
  const saldo = parsearImporteDesdeApi(saldoApi)
  if (saldo.isZero()) {
    return `Saldo ${formatearMonto('0.00')}`
  }
  const rotulos = ROTULOS_DE_SALDO[cuentaTipo]
  const rotulo = saldo.isNegative() ? rotulos.aFavor : rotulos.deuda
  return `${rotulo} $ ${formatearImporte(saldo.abs())}`
}

export function etiquetasDeSentido(cuentaTipo: CuentaTipo): Record<Sentido, string> {
  return ETIQUETAS_DE_SENTIDO[cuentaTipo]
}

/** El tipo del catálogo (CC-02, CC-03) en palabras; uno que la pantalla no
 * conoce todavía se muestra tal cual en vez de esconderse. */
export function etiquetaDeTipo(tipo: string): string {
  return ETIQUETAS_DE_TIPO[tipo] ?? tipo
}

/** Reparte el importe de un movimiento en la columna de aumento o en la de
 * reducción (spec: "columnas de aumento y reducción"). */
export function columnasDeMovimiento(movimiento: { sentido: string; importe: string }): {
  aumento: string | null
  reduccion: string | null
} {
  const monto = formatearMonto(movimiento.importe)
  return movimiento.sentido === 'AUMENTA' ? { aumento: monto, reduccion: null } : { aumento: null, reduccion: monto }
}
