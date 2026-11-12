/**
 * Cuentas de la pantalla de venta (change 18a, tarea 12.1; `design.md` D8, D12, D21; PRC-22,
 * VTA-04, VTA-11, CC-04). Todo con `decimal.js` desde `lib/money.ts` (INV-03): ningún importe
 * pasa por `number`. En modo impositivo A (el único soportado, D13) el total es la suma de los
 * brutos menos los descuentos; la pantalla de 18a no aplica descuentos propios y, si el servidor
 * resuelve otro total, responde `PRECIO_DIFIERE` y se muestra el suyo (D2).
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { formatearMonto } from '../cuentas-corrientes/presentacion'
import { sumarMedios, type MedioDePagoDeFormulario } from '../pagos-proveedores/formularioPago'
import { calcularBrutoDeLinea } from '../precios/brutoDeLinea'

/** PRC-22: bruto de una línea; un único redondeo, igual que el servidor. */
export function calcularBrutoDelPedido(precioReferencia: string, unidadesReferencia: number, cantidadBase: number): Importe {
  return calcularBrutoDeLinea(precioReferencia, unidadesReferencia, cantidadBase)
}

/** Total de la venta: suma de los brutos de las líneas (VTA-04, modo A, sin descuentos). */
export function totalDelPedido(brutos: readonly Importe[]): Importe {
  return redondearImporte(brutos.reduce((acumulado, bruto) => acumulado.add(bruto), parsearImporteDesdeApi('0')))
}

/** Importe de la cobranza en el acto: la suma de sus medios (INV-08, D12). */
export function sumarCobranzaDeVenta(medios: readonly MedioDePagoDeFormulario[]): Importe {
  return sumarMedios(medios)
}

/** Saldo del cliente después de la venta y su cobranza: saldo + total - cobrado (CC-04; negativo es a favor). */
export function calcularSaldoResultanteDeVenta(saldoActual: string, total: string, cobrado: string): Importe {
  return redondearImporte(
    parsearImporteDesdeApi(saldoActual).add(parsearImporteDesdeApi(total)).sub(parsearImporteDesdeApi(cobrado)),
  )
}

/** `"Queda debiendo $ 161.250,00"`, `"Saldo a favor $ 500,00"` o `"Saldo $ 0,00"`. */
export function textoDeSaldoResultanteDeVenta(saldoActual: string, total: string, cobrado: string): string {
  const resultante = calcularSaldoResultanteDeVenta(saldoActual, total, cobrado)
  if (resultante.isZero()) return `Saldo ${formatearMonto('0.00')}`
  if (resultante.isNegative()) return `Saldo a favor ${formatearMonto(resultante.neg().toFixed(2))}`
  return `Queda debiendo ${formatearMonto(resultante.toFixed(2))}`
}

/** Aviso de la confirmación explícita (VTA-11); `null` cuando el saldo no queda a favor. */
export function avisoDeSaldoAFavorTrasVenta(saldoActual: string, total: string, cobrado: string): string | null {
  const resultante = calcularSaldoResultanteDeVenta(saldoActual, total, cobrado)
  return resultante.isNegative() ? `Le queda saldo a favor de ${formatearMonto(resultante.neg().toFixed(2))}` : null
}

export const AVISO_CONSUMIDOR_FINAL_DE_CONTADO =
  'Al consumidor final se le vende solo de contado: lo cobrado tiene que ser igual al total.'

export const FALTA_CONTADO_DE_CONSUMIDOR_FINAL = 'Cargá una cobranza igual al total para poder confirmar.'

export interface ContadoDeConsumidorFinal {
  /** El cliente elegido es el consumidor final. */
  aplica: boolean
  /** No aplica, o la cobranza en el acto es igual al total (espeja `CONSUMIDOR_FINAL_CONTADO`, D5). */
  cumple: boolean
}

/** CLI-03, D5: el consumidor final se vende solo de contado; con otro cliente no se exige nada. */
export function evaluarContadoDeConsumidorFinal(esConsumidorFinal: boolean, total: string, cobrado: string): ContadoDeConsumidorFinal {
  if (!esConsumidorFinal) return { aplica: false, cumple: true }
  return { aplica: true, cumple: parsearImporteDesdeApi(cobrado).eq(parsearImporteDesdeApi(total)) }
}

export type LecturaDeSaldoDeCliente =
  | { estado: 'cargando' }
  | { estado: 'error' }
  | { estado: 'leido'; saldo: string }

export type ConfirmacionDeVenta =
  | { tipo: 'ninguna' }
  | { tipo: 'saldo-a-favor'; mensaje: string }
  | { tipo: 'saldo-ilegible'; mensaje: string }
  | { tipo: 'esperar' }

export const AVISO_SALDO_ILEGIBLE_DE_VENTA =
  'No pudimos leer el saldo del cliente; no podemos avisarte si lo cobrado supera lo que debe.'

/**
 * Qué confirmación corresponde antes de enviar según lo que se sabe del saldo (VTA-11): cobrar de
 * más sigue permitido pero nunca sin aviso; con el saldo ilegible se pide confirmar si se cobra
 * más que el total de la venta.
 */
export function decidirConfirmacionDeVenta(
  lectura: LecturaDeSaldoDeCliente,
  total: string,
  cobrado: string,
): ConfirmacionDeVenta {
  switch (lectura.estado) {
    case 'cargando':
      return { tipo: 'esperar' }
    case 'error':
      return parsearImporteDesdeApi(cobrado).gt(parsearImporteDesdeApi(total))
        ? { tipo: 'saldo-ilegible', mensaje: AVISO_SALDO_ILEGIBLE_DE_VENTA }
        : { tipo: 'ninguna' }
    case 'leido': {
      const mensaje = avisoDeSaldoAFavorTrasVenta(lectura.saldo, total, cobrado)
      return mensaje === null ? { tipo: 'ninguna' } : { tipo: 'saldo-a-favor', mensaje }
    }
  }
}
