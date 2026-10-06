/**
 * Lógica pura del formulario de pago a proveedor (change 12, tarea 8.1; `design.md` D3, D4,
 * D6, D8; spec `administracion-de-pagos`). Nada de esto vive en los componentes
 * (`CLAUDE.md` §5): la pantalla llama a estas funciones y pinta el resultado.
 *
 * Los importes nunca pasan por `number` (INV-03): se parsean con `parsearImporteDesdeApi`
 * y se calcula con `decimal.js`. El servidor valida igual (TR-10); esto es UX.
 */

import { z } from 'zod'

import type { components } from '../../api/schema.gen'
import type { Importe } from '../../lib/money'
import { EntradaNoEsDineroExactoError, parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { formatearMonto, textoDeSaldo } from '../cuentas-corrientes/presentacion'

export interface MedioDePagoDeFormulario {
  medioPagoId: string
  importe: string
  referencia: string
}

/** El pago tal como lo edita el usuario: todo texto. */
export interface FormularioDePago {
  proveedorId: string
  /** Fecha de negocio `aaaa-mm-dd`. */
  fecha: string
  importe: string
  observacion: string
  medios: MedioDePagoDeFormulario[]
}

export interface ContextoDePago {
  /** Fecha de negocio de hoy `aaaa-mm-dd`: la fecha del pago no puede ser posterior (D4). */
  hoy: string
  /** Ids de los medios de pago que exigen referencia (`requiere_referencia`). */
  mediosQueRequierenReferencia: ReadonlySet<string>
}

const MAXIMO_DE_MEDIOS = 20
const MAXIMO_DE_OBSERVACION = 500

function importeOCero(texto: string): Importe {
  try {
    return parsearImporteDesdeApi(texto.trim())
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) return parsearImporteDesdeApi('0')
    throw error
  }
}

/** Suma de los importes de los medios; uno vacío o inválido cuenta como cero. */
export function sumarMedios(medios: readonly MedioDePagoDeFormulario[]): Importe {
  return redondearImporte(medios.reduce((acumulado, medio) => acumulado.add(importeOCero(medio.importe)), parsearImporteDesdeApi('0')))
}

/**
 * Lo que falta (positivo) o sobra (negativo) para que los medios sumen el importe del
 * pago (INV-08, PAG-01).
 */
export function calcularFaltanteDeMedios(importe: string, medios: readonly MedioDePagoDeFormulario[]): Importe {
  return redondearImporte(importeOCero(importe).sub(sumarMedios(medios)))
}

/** `"Faltan $ 52.460,00"`, `"Sobran $ 180,00"` o `"Los medios suman el importe."`. */
export function etiquetaDeDiferencia(faltante: Importe): string {
  if (faltante.isZero()) return 'Los medios suman el importe.'
  if (faltante.gt(0)) return `Faltan ${formatearMonto(faltante.toFixed(2))}`
  return `Sobran ${formatearMonto(faltante.neg().toFixed(2))}`
}

/** Saldo del proveedor después de pagar `importe` (CC-04: positivo es lo que le debemos). */
export function calcularSaldoResultante(saldoActual: string, importe: string): Importe {
  return redondearImporte(parsearImporteDesdeApi(saldoActual).sub(importeOCero(importe)))
}

/** `"Le debemos $ 53.720,00"`, `"Saldo a nuestro favor $ 6.280,00"` o `"Saldo $ 0,00"`. */
export function textoDeSaldoResultante(saldoActual: string, importe: string): string {
  return textoDeSaldo('PROVEEDOR', calcularSaldoResultante(saldoActual, importe).toFixed(2))
}

/** Monto que queda a favor de la organización tras el pago, o `null` si no queda ninguno (D3). */
export function saldoAFavorTrasPago(saldoActual: string, importe: string): Importe | null {
  const resultante = calcularSaldoResultante(saldoActual, importe)
  return resultante.isNegative() ? resultante.neg() : null
}

/** Aviso de la confirmación explícita (D3); `null` cuando el saldo no queda a favor. */
export function avisoDeSaldoAFavorTrasPago(saldoActual: string, importe: string): string | null {
  const aFavor = saldoAFavorTrasPago(saldoActual, importe)
  return aFavor === null ? null : `Queda saldo a nuestro favor de ${formatearMonto(aFavor.toFixed(2))}`
}

function esImporteValido(texto: string): boolean {
  try {
    const valor = parsearImporteDesdeApi(texto.trim())
    return texto.trim() !== '' && valor.gt(0) && valor.decimalPlaces() <= 2
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) return false
    throw error
  }
}

/**
 * Esquema Zod del formulario (PAG-01, D4, D6): proveedor, fecha no futura, importe positivo
 * con dos decimales como máximo, de 1 a 20 medios con importe positivo y referencia
 * obligatoria donde el medio la exige, y observación de hasta 500 caracteres. La suma de
 * los medios contra el importe es `calcularFaltanteDeMedios`, aparte, porque la pantalla la
 * muestra mientras se tipea.
 */
export function crearEsquemaDePago(contexto: ContextoDePago) {
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
    proveedorId: z.string().min(1, 'Elegí un proveedor.'),
    fecha: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/, 'Ingresá la fecha del pago.')
      .refine((fecha) => fecha <= contexto.hoy, 'La fecha del pago no puede ser posterior a hoy.'),
    importe: z.string().refine(esImporteValido, 'Ingresá un importe mayor que cero, con hasta dos decimales.'),
    observacion: z.string().max(MAXIMO_DE_OBSERVACION, 'La observación admite hasta 500 caracteres.'),
    medios: z
      .array(medio)
      .min(1, 'Cargá al menos un medio de pago.')
      .max(MAXIMO_DE_MEDIOS, 'Un pago admite hasta 20 medios.'),
  })
}

/**
 * Si el formulario está en condiciones de enviarse: el esquema pasa y los medios suman
 * exactamente el importe (INV-08).
 */
export function puedeRegistrarPago(formulario: FormularioDePago, contexto: ContextoDePago): boolean {
  return (
    crearEsquemaDePago(contexto).safeParse(formulario).success &&
    calcularFaltanteDeMedios(formulario.importe, formulario.medios).isZero()
  )
}

function textoONulo(texto: string): string | null {
  const recortado = texto.trim()
  return recortado === '' ? null : recortado
}

/** Cuerpo de `PAGO_PROVEEDOR_REGISTRAR` (`POST /pagos-proveedores`); los importes viajan como string. */
export function construirSolicitudDePago(
  formulario: FormularioDePago,
): components['schemas']['PagoProveedorRegistrarRequest'] {
  return {
    proveedor_id: formulario.proveedorId,
    fecha: formulario.fecha,
    importe: redondearImporte(formulario.importe.trim()).toFixed(2),
    observacion: textoONulo(formulario.observacion),
    medios: formulario.medios.map((medio) => ({
      medio_pago_id: medio.medioPagoId,
      importe: redondearImporte(medio.importe.trim()).toFixed(2),
      referencia: textoONulo(medio.referencia),
    })),
  }
}
