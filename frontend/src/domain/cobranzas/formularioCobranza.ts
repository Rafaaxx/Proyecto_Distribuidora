/**
 * Lógica pura del formulario de cobranza (change 17, tarea 14.2; `design.md` D2, D5, D19;
 * spec `administracion-de-cobranzas`). Nada de esto vive en los componentes (`CLAUDE.md` §5).
 *
 * Los importes nunca pasan por `number` (INV-03): se parsean con `lib/money.ts` y se calcula con
 * `decimal.js`. La suma de medios y su faltante son las del pago a proveedor (misma regla
 * INV-08, `design.md` D17). El servidor valida igual (TR-10); esto es UX.
 */

import { z } from 'zod'

import type { components } from '../../api/schema.gen'
import type { Importe } from '../../lib/money'
import { EntradaNoEsDineroExactoError, parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { formatearMonto } from '../cuentas-corrientes/presentacion'
import {
  calcularFaltanteDeMedios,
  esImporteValido,
  type MedioDePagoDeFormulario,
} from '../pagos-proveedores/formularioPago'

export { calcularFaltanteDeMedios }
export type { MedioDePagoDeFormulario }

/** La cobranza tal como la edita el usuario: todo texto. */
export interface FormularioDeCobranza {
  clienteId: string
  importe: string
  observacion: string
  medios: MedioDePagoDeFormulario[]
}

export interface ContextoDeCobranza {
  /** Ids de los medios de pago que exigen referencia (`requiere_referencia`). */
  mediosQueRequierenReferencia: ReadonlySet<string>
}

const MAXIMO_DE_MEDIOS = 20
const MAXIMO_DE_OBSERVACION = 500

export const AVISO_SALDO_ILEGIBLE_DE_CLIENTE =
  'No pudimos leer el saldo del cliente; no podemos avisarte si esta cobranza supera su deuda.'

function importeOCero(texto: string): Importe {
  try {
    return parsearImporteDesdeApi(texto.trim())
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) return parsearImporteDesdeApi('0')
    throw error
  }
}

/** `"Falta $ 20.000,00"`, `"Falta $ 0,00"` (los medios suman) o `"Sobra $ 1.000,50"` (COB-02). */
export function etiquetaDeFaltante(faltante: Importe): string {
  if (faltante.isNegative()) return `Sobra ${formatearMonto(faltante.neg().toFixed(2))}`
  return `Falta ${formatearMonto(faltante.toFixed(2))}`
}

/** Saldo del cliente después de cobrar `importe` (CC-04: positivo es lo que nos debe). */
export function calcularSaldoResultante(saldoActual: string, importe: string): Importe {
  return redondearImporte(parsearImporteDesdeApi(saldoActual).sub(importeOCero(importe)))
}

/** `"Queda debiendo $ 100.000,00"`, `"Saldo a favor $ 10.000,00"` o `"Saldo $ 0,00"`. */
export function textoDeSaldoResultante(saldoActual: string, importe: string): string {
  const resultante = calcularSaldoResultante(saldoActual, importe)
  if (resultante.isZero()) return `Saldo ${formatearMonto('0.00')}`
  if (resultante.isNegative()) return `Saldo a favor ${formatearMonto(resultante.neg().toFixed(2))}`
  return `Queda debiendo ${formatearMonto(resultante.toFixed(2))}`
}

/** Aviso de la confirmación explícita (COB-03, D5); `null` cuando el saldo no queda a favor. */
export function avisoDeSaldoAFavorTrasCobranza(saldoActual: string, importe: string): string | null {
  const resultante = calcularSaldoResultante(saldoActual, importe)
  return resultante.isNegative() ? `Le queda saldo a favor de ${formatearMonto(resultante.neg().toFixed(2))}` : null
}

export type LecturaDeSaldoDeCliente =
  | { estado: 'cargando' }
  | { estado: 'error' }
  | { estado: 'leido'; saldo: string }

export type ConfirmacionDeCobranza =
  | { tipo: 'ninguna' }
  | { tipo: 'saldo-a-favor'; mensaje: string }
  | { tipo: 'saldo-ilegible'; mensaje: string }
  | { tipo: 'esperar' }

/**
 * Qué confirmación corresponde antes de enviar según lo que se sabe del saldo (COB-03, D5): cobrar
 * de más sigue permitido pero nunca sin aviso; con el saldo ilegible se pide confirmar igual.
 */
export function decidirConfirmacionDeCobranza(lectura: LecturaDeSaldoDeCliente, importe: string): ConfirmacionDeCobranza {
  switch (lectura.estado) {
    case 'cargando':
      return { tipo: 'esperar' }
    case 'error':
      return { tipo: 'saldo-ilegible', mensaje: AVISO_SALDO_ILEGIBLE_DE_CLIENTE }
    case 'leido': {
      const mensaje = avisoDeSaldoAFavorTrasCobranza(lectura.saldo, importe)
      return mensaje === null ? { tipo: 'ninguna' } : { tipo: 'saldo-a-favor', mensaje }
    }
  }
}

/**
 * Esquema Zod del formulario (COB-01, COB-02): cliente, importe positivo con dos decimales como
 * máximo, de 1 a 20 medios con importe positivo y referencia obligatoria donde el medio la
 * exige, y observación de hasta 500 caracteres. La suma de los medios contra el importe es
 * `calcularFaltanteDeMedios`, aparte, porque la pantalla la muestra mientras se tipea.
 */
export function crearEsquemaDeCobranza(contexto: ContextoDeCobranza) {
  const medio = z
    .object({
      medioPagoId: z.string().min(1, 'Elegí un medio de pago.'),
      importe: z.string().refine(esImporteValido, 'Ingresá un importe mayor que cero, con hasta dos decimales.'),
      referencia: z.string(),
    })
    .refine((m) => !contexto.mediosQueRequierenReferencia.has(m.medioPagoId) || m.referencia.trim() !== '', {
      path: ['referencia'],
      message: 'La referencia es obligatoria para este medio de pago.',
    })

  return z.object({
    clienteId: z.string().min(1, 'Elegí un cliente.'),
    importe: z.string().refine(esImporteValido, 'Ingresá un importe mayor que cero, con hasta dos decimales.'),
    observacion: z.string().max(MAXIMO_DE_OBSERVACION, 'La observación admite hasta 500 caracteres.'),
    medios: z
      .array(medio)
      .min(1, 'Cargá al menos un medio de pago.')
      .max(MAXIMO_DE_MEDIOS, 'Una cobranza admite hasta 20 medios.'),
  })
}

/** El esquema pasa y los medios suman exactamente el importe (INV-08). */
export function puedeRegistrarCobranza(formulario: FormularioDeCobranza, contexto: ContextoDeCobranza): boolean {
  return (
    crearEsquemaDeCobranza(contexto).safeParse(formulario).success &&
    calcularFaltanteDeMedios(formulario.importe, formulario.medios).isZero()
  )
}

function textoONulo(texto: string): string | null {
  const recortado = texto.trim()
  return recortado === '' ? null : recortado
}

/** Cuerpo de `COBRANZA_REGISTRAR` (`POST /cobranzas`); los importes viajan como string (INV-03). */
export function construirSolicitudDeCobranza(
  formulario: FormularioDeCobranza,
  cobranzaId: string,
): components['schemas']['CobranzaRegistrarRequest'] {
  return {
    cobranza_id: cobranzaId,
    cliente_id: formulario.clienteId,
    importe: redondearImporte(formulario.importe.trim()).toFixed(2),
    observacion: textoONulo(formulario.observacion),
    medios: formulario.medios.map((medio) => ({
      medio_pago_id: medio.medioPagoId,
      importe: redondearImporte(medio.importe.trim()).toFixed(2),
      referencia: textoONulo(medio.referencia),
    })),
  }
}
