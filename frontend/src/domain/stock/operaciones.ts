import { z } from 'zod'

import type { components } from '../../api/schema.gen'
import type { CodigoPermiso } from '../identidad/permisos'
import { aUnidadesBase } from './cantidades'
import { MAXIMO_DE_LINEAS, parteEntera } from './stockInicial'
import { etiquetaDeTipoDeMovimiento } from './ubicacionSchema'

/**
 * Transferencias y ajustes de stock (change 14, grupo 12; `design.md` D1, D2, D5, D6, D7,
 * D11). Una línea se escribe en cajas + unidades y se convierte a unidad base entera
 * (CAT-08, INV-04); el saldo actual y el resultante se calculan con enteros; los esquemas Zod
 * validan lo que el servidor vuelve a validar siempre (TR-10). Lógica pura, sin React ni
 * `number` para costos: acá no hay importes.
 */

export type CuerpoTransferencia = components['schemas']['TransferenciaCrearRequest']
export type CuerpoAjuste = components['schemas']['AjusteCrearRequest']

/** Ámbitos de motivo que usan estas pantallas (lista cerrada del servidor). */
export const AMBITO_DE_AJUSTE = 'AJUSTE_STOCK'
export const AMBITO_DE_ANULACION_DE_TRANSFERENCIA = 'ANULACION_TRANSFERENCIA'
export const AMBITO_DE_ANULACION_DE_AJUSTE = 'ANULACION_AJUSTE'

export const ESTADO_CONFIRMADA = 'CONFIRMADA'
export const ESTADO_ANULADA = 'ANULADA'

const ETIQUETAS_DE_ESTADO: Record<string, string> = { CONFIRMADA: 'Confirmada', ANULADA: 'Anulada' }

/** El estado de una transferencia o un ajuste en palabras; uno desconocido se muestra tal cual. */
export function etiquetaDeEstado(estado: string): string {
  return ETIQUETAS_DE_ESTADO[estado] ?? estado
}

const LIMITE_DE_OBSERVACION = 500

// --- línea y cantidades -------------------------------------------------------

/** Una línea tal como la escribe el usuario, con la presentación de referencia de su producto. */
export interface LineaDeEntrada {
  productoId: string
  cajas: string
  unidades: string
  /** Faltante: la cantidad se envía con signo negativo (solo el ajuste lo admite). */
  negativa: boolean
  unidadesPorCaja: number | null
  nombrePresentacion: string | null
}

export type ResultadoDeCantidad = { ok: true; cantidadBase: number } | { ok: false; mensaje: string }

/** Cajas + unidades a unidad base entera, con el signo de la línea. No valida que sea distinta de cero. */
export function cantidadDeLinea(linea: LineaDeEntrada): ResultadoDeCantidad {
  if (linea.productoId === '') return { ok: false, mensaje: 'Elegí un producto.' }
  const cajas = parteEntera(linea.cajas, linea.nombrePresentacion ?? 'Cajas')
  if (typeof cajas === 'string') return { ok: false, mensaje: cajas }
  const unidades = parteEntera(linea.unidades, 'Unidades')
  if (typeof unidades === 'string') return { ok: false, mensaje: unidades }
  try {
    const magnitud = aUnidadesBase(cajas, unidades, linea.unidadesPorCaja)
    return { ok: true, cantidadBase: linea.negativa ? -magnitud : magnitud }
  } catch (error) {
    return { ok: false, mensaje: error instanceof Error ? error.message : 'La cantidad no es válida.' }
  }
}

// --- saldos -------------------------------------------------------------------

export interface SaldoDeLinea {
  actual: number
  resultante: number
  negativo: boolean
}

function saldo(actual: number, variacion: number): SaldoDeLinea {
  const resultante = actual + variacion
  return { actual, resultante, negativo: resultante < 0 }
}

/** Saldo actual y resultante de una línea de ajuste (con signo). */
export function previsualizarAjuste(saldoActual: number, cantidadBase: number): SaldoDeLinea {
  return saldo(saldoActual, cantidadBase)
}

/** Saldo actual y resultante de una línea de transferencia en origen (resta) y destino (suma). */
export function previsualizarTransferencia(
  saldoOrigen: number,
  saldoDestino: number,
  cantidadBase: number,
): { origen: SaldoDeLinea; destino: SaldoDeLinea } {
  return { origen: saldo(saldoOrigen, -cantidadBase), destino: saldo(saldoDestino, cantidadBase) }
}

/** D2: la cantidad positiva que lleva a cero un saldo negativo; `null` si el saldo no es negativo. */
export function cantidadParaLlevarACero(saldoActual: number): number | null {
  return saldoActual < 0 ? -saldoActual : null
}

// --- esquemas -----------------------------------------------------------------

const observacion = z.string().trim().max(LIMITE_DE_OBSERVACION, `La observación admite hasta ${String(LIMITE_DE_OBSERVACION)} caracteres.`)
const MENSAJE_DE_LINEAS = `Una operación admite hasta ${String(MAXIMO_DE_LINEAS)} líneas.`

function productosNoRepetidos(lineas: { productoId: string }[], contexto: z.RefinementCtx) {
  const vistos = new Set<string>()
  for (const [indice, { productoId }] of lineas.entries()) {
    if (vistos.has(productoId)) {
      contexto.addIssue({
        code: 'custom',
        message: 'Un producto no puede repetirse en la misma operación.',
        path: ['lineas', indice, 'productoId'],
      })
    }
    vistos.add(productoId)
  }
}

const lineasDeTransferencia = z
  .array(
    z.object({
      productoId: z.string().min(1, 'Elegí un producto.'),
      cantidadBase: z.number().int().positive('La cantidad tiene que ser mayor que cero.'),
    }),
  )
  .min(1, 'Agregá al menos una línea.')
  .max(MAXIMO_DE_LINEAS, MENSAJE_DE_LINEAS)

export const esquemaTransferencia = z
  .object({
    ubicacionOrigenId: z.string().min(1, 'Elegí el origen.'),
    ubicacionDestinoId: z.string().min(1, 'Elegí el destino.'),
    observacion,
    lineas: lineasDeTransferencia,
  })
  .superRefine((datos, contexto) => {
    if (datos.ubicacionOrigenId !== '' && datos.ubicacionOrigenId === datos.ubicacionDestinoId) {
      contexto.addIssue({
        code: 'custom',
        message: 'El origen y el destino tienen que ser distintos.',
        path: ['ubicacionDestinoId'],
      })
    }
    productosNoRepetidos(datos.lineas, contexto)
  })

export const esquemaAjuste = z
  .object({
    ubicacionId: z.string().min(1, 'Elegí la ubicación.'),
    motivoId: z.string().min(1, 'Elegí un motivo.'),
    observacion,
    lineas: z
      .array(
        z.object({
          productoId: z.string().min(1, 'Elegí un producto.'),
          cantidadBase: z
            .number()
            .int()
            .refine((cantidad) => cantidad !== 0, 'La cantidad no puede ser cero.'),
        }),
      )
      .min(1, 'Agregá al menos una línea.')
      .max(MAXIMO_DE_LINEAS, MENSAJE_DE_LINEAS),
  })
  .superRefine((datos, contexto) => {
    productosNoRepetidos(datos.lineas, contexto)
  })

/** Diálogo de anulación (transferencia o ajuste): el motivo es obligatorio. */
export const esquemaAnulacion = z.object({ motivoId: z.string().min(1, 'Elegí un motivo.') })

// --- armado del envío ---------------------------------------------------------

export type ResultadoDeArmado<Cuerpo> =
  | { ok: true; cuerpo: Cuerpo }
  | { ok: false; mensaje: string; indice?: number }

function fallo(error: z.ZodError): { ok: false; mensaje: string; indice?: number } {
  const primero = error.issues[0]
  const mensaje = primero?.message ?? 'Los datos no son válidos.'
  const [raiz, indice] = primero?.path ?? []
  return raiz === 'lineas' && typeof indice === 'number' ? { ok: false, mensaje, indice } : { ok: false, mensaje }
}

function convertirLineas(
  lineas: LineaDeEntrada[],
  conSigno: boolean,
): { ok: true; lineas: { productoId: string; cantidadBase: number }[] } | { ok: false; mensaje: string; indice: number } {
  const convertidas: { productoId: string; cantidadBase: number }[] = []
  for (const [indice, linea] of lineas.entries()) {
    const cantidad = cantidadDeLinea(conSigno ? linea : { ...linea, negativa: false })
    if (!cantidad.ok) return { ok: false, mensaje: cantidad.mensaje, indice }
    convertidas.push({ productoId: linea.productoId, cantidadBase: cantidad.cantidadBase })
  }
  return { ok: true, lineas: convertidas }
}

function conObservacion<Cuerpo extends object>(cuerpo: Cuerpo, texto: string): Cuerpo & { observacion?: string } {
  return texto === '' ? cuerpo : { ...cuerpo, observacion: texto }
}

export interface EntradaDeTransferencia {
  origenId: string
  destinoId: string
  observacion: string
  lineas: LineaDeEntrada[]
}

/** Valida y arma `TransferenciaCrearRequest`: 1 a 200 líneas, sin repetir producto, cantidades positivas. */
export function armarTransferencia(entrada: EntradaDeTransferencia): ResultadoDeArmado<CuerpoTransferencia> {
  const convertidas = convertirLineas(entrada.lineas, false)
  if (!convertidas.ok) return convertidas
  const validado = esquemaTransferencia.safeParse({
    ubicacionOrigenId: entrada.origenId,
    ubicacionDestinoId: entrada.destinoId,
    observacion: entrada.observacion,
    lineas: convertidas.lineas,
  })
  if (!validado.success) return fallo(validado.error)
  const datos = validado.data
  return {
    ok: true,
    cuerpo: conObservacion(
      {
        ubicacion_origen_id: datos.ubicacionOrigenId,
        ubicacion_destino_id: datos.ubicacionDestinoId,
        lineas: datos.lineas.map((l) => ({ producto_id: l.productoId, cantidad_base: l.cantidadBase })),
      },
      datos.observacion,
    ),
  }
}

export interface EntradaDeAjuste {
  ubicacionId: string
  motivoId: string
  observacion: string
  lineas: LineaDeEntrada[]
}

/** Valida y arma `AjusteCrearRequest`: líneas con signo y distintas de cero, motivo obligatorio. */
export function armarAjuste(entrada: EntradaDeAjuste): ResultadoDeArmado<CuerpoAjuste> {
  const convertidas = convertirLineas(entrada.lineas, true)
  if (!convertidas.ok) return convertidas
  const validado = esquemaAjuste.safeParse({
    ubicacionId: entrada.ubicacionId,
    motivoId: entrada.motivoId,
    observacion: entrada.observacion,
    lineas: convertidas.lineas,
  })
  if (!validado.success) return fallo(validado.error)
  const datos = validado.data
  return {
    ok: true,
    cuerpo: conObservacion(
      {
        ubicacion_id: datos.ubicacionId,
        motivo_id: datos.motivoId,
        lineas: datos.lineas.map((l) => ({ producto_id: l.productoId, cantidad_base: l.cantidadBase })),
      },
      datos.observacion,
    ),
  }
}

// --- quién puede anular -------------------------------------------------------

/** Lo único que necesitan estas reglas de `usePermisos()`. */
export interface PermisosConsultables {
  tiene(permiso: CodigoPermiso): boolean
}

/**
 * Misma regla que el dominio del backend (D5, D5.4): `TRANSFERIR_STOCK` siempre; la transferencia
 * de otro usuario además exige `ANULAR_TRANSFERENCIA`. Ocultar el botón es comodidad: el servidor
 * decide (SEG-06).
 */
export function puedeAnularTransferencia(
  creadorId: string,
  usuarioId: string,
  permisos: PermisosConsultables,
): boolean {
  if (!permisos.tiene('TRANSFERIR_STOCK')) return false
  return creadorId === usuarioId || permisos.tiene('ANULAR_TRANSFERENCIA')
}

/** Un ajuste, propio o ajeno, lo anula quien tiene `AJUSTAR_STOCK` (D5). */
export function puedeAnularAjuste(permisos: PermisosConsultables): boolean {
  return permisos.tiene('AJUSTAR_STOCK')
}

// --- kardex -------------------------------------------------------------------

const ROTULOS_DE_ANULACION: Record<string, string> = {
  ANULACION_TRANSFERENCIA: 'Anulación de transferencia',
  ANULACION_AJUSTE_STOCK: 'Anulación de ajuste',
}

/**
 * Rótulo de un movimiento del kardex: los inversos de una anulación (D5.1) se distinguen por su
 * `origen_tipo`; el resto usa la etiqueta de su tipo (STK-03).
 */
export function rotuloDeMovimiento(tipo: string, origenTipo: string): string {
  return ROTULOS_DE_ANULACION[origenTipo] ?? etiquetaDeTipoDeMovimiento(tipo)
}

/**
 * Ruta del detalle de la transferencia o del ajuste que originó un movimiento, solo si el usuario
 * tiene el permiso de lectura correspondiente (D7, ADR-027); `null` si no corresponde.
 */
export function enlaceDeOperacion(origenTipo: string, origenId: string, permisos: PermisosConsultables): string | null {
  if (origenTipo === 'TRANSFERENCIA' || origenTipo === 'ANULACION_TRANSFERENCIA') {
    return permisos.tiene('TRANSFERIR_STOCK') ? `/admin/stock/transferencias/${origenId}` : null
  }
  if (origenTipo === 'AJUSTE_STOCK' || origenTipo === 'ANULACION_AJUSTE_STOCK') {
    return permisos.tiene('AJUSTAR_STOCK') ? `/admin/stock/ajustes/${origenId}` : null
  }
  return null
}
