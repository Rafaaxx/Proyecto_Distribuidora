/**
 * Rendición de una jornada (change 24, `design.md` D2, D4; RUT-06, RUT-07, STK-04, INV-04):
 * lo que la pantalla de conteo calcula al escribir. Lógica pura sobre cantidades enteras en
 * unidad base; el servidor valida y es la autoridad (el esperado y el conjunto a contar son
 * suyos, SEG-06). Las cantidades no son dinero: no pasan por `decimal.js`.
 */

import { desdeUnidadesBase, type ReferenciaDePresentacion } from './cantidades'
import { cantidadDeLinea } from './operaciones'

/** RUT-07: al abrir + ingresos − ventas + anulaciones + otros. */
export function calcularEsperado(componentes: {
  alAbrir: number
  ingresos: number
  ventas: number
  anulaciones: number
  otros: number
}): number {
  const { alAbrir, ingresos, ventas, anulaciones, otros } = componentes
  return alAbrir + ingresos - ventas + anulaciones + otros
}

/**
 * INV-04, RUT-06: contado menos esperado, con signo. Sin una cantidad contada entera y no
 * negativa todavía no hay diferencia (`null`).
 */
export function calcularDiferencia(contada: number | null, esperada: number): number | null {
  if (contada === null || !Number.isInteger(contada) || contada < 0) return null
  return contada - esperada
}

/**
 * RUT-06: los productos del conjunto a contar que el conteo todavía no trae, en el orden del
 * conjunto. Los productos contados de más son sobrantes y no cuentan.
 */
export function productosFaltantes(
  conjunto: readonly string[],
  contados: readonly string[],
): string[] {
  const presentes = new Set(contados)
  return conjunto.filter((producto) => !presentes.has(producto))
}

// --- la pantalla de conteo y el diálogo de cierre (change 24, D2, D6, D9) ---------------------

/** Una fila de la pantalla de conteo tal como la escribe quien cuenta (cajas + unidades, CAT-08). */
export interface FilaDeConteo {
  productoId: string
  /** El esperado que muestra la pantalla, en unidad base. */
  esperado: number
  cajas: string
  unidades: string
  unidadesPorCaja: number | null
  nombrePresentacion: string | null
}

export interface LineaDeConteo {
  producto_id: string
  cantidad_contada: number
  cantidad_esperada: number
}

export type ResultadoDeConteo =
  | { ok: true; lineas: LineaDeConteo[]; conDiferencias: number }
  | { ok: false; sinContar: string[]; invalidas: { productoId: string; mensaje: string }[] }

function sinEscribir(fila: { cajas: string; unidades: string }): boolean {
  return fila.cajas.trim() === '' && fila.unidades.trim() === ''
}

/** Lo contado en unidad base; `null` si todavía no se escribió algo válido (sin diferencia que mostrar). */
export function contadoEnBase(fila: Pick<FilaDeConteo, 'cajas' | 'unidades' | 'productoId' | 'unidadesPorCaja' | 'nombrePresentacion'>): number | null {
  if (sinEscribir(fila)) return null
  const cantidad = cantidadDeLinea({ ...fila, negativa: false })
  return cantidad.ok ? cantidad.cantidadBase : null
}

/**
 * RUT-06: convierte lo escrito a unidad base. Una fila sin nada escrito no está contada (no se
 * toma como cero: un cero hay que escribirlo, D2); un valor que no es un entero no negativo es
 * inválido. Sin filas en falta ni inválidas devuelve las líneas del conteo y cuántas tienen
 * diferencia. El servidor vuelve a validar todo (SEG-06).
 */
export function armarConteo(filas: readonly FilaDeConteo[]): ResultadoDeConteo {
  const sinContar: string[] = []
  const invalidas: { productoId: string; mensaje: string }[] = []
  const lineas: LineaDeConteo[] = []
  for (const fila of filas) {
    if (sinEscribir(fila)) {
      sinContar.push(fila.productoId)
      continue
    }
    const cantidad = cantidadDeLinea({ ...fila, negativa: false })
    if (!cantidad.ok) {
      invalidas.push({ productoId: fila.productoId, mensaje: cantidad.mensaje })
      continue
    }
    lineas.push({ producto_id: fila.productoId, cantidad_contada: cantidad.cantidadBase, cantidad_esperada: fila.esperado })
  }
  if (sinContar.length > 0 || invalidas.length > 0) return { ok: false, sinContar, invalidas }
  return { ok: true, lineas, conDiferencias: lineas.filter((l) => l.cantidad_contada !== l.cantidad_esperada).length }
}

/** D9 (aprobados en 0.2): «¿Registrar la rendición con {N} diferencias?» o «sin diferencias». */
export function textoDeConfirmacionDeRendicion(diferencias: number): string {
  if (diferencias === 0) return '¿Registrar la rendición sin diferencias?'
  return `¿Registrar la rendición con ${String(diferencias)} ${diferencias === 1 ? 'diferencia' : 'diferencias'}?`
}

/** Una fila de la devolución del remanente: la cantidad que se devuelve, en cajas + unidades. */
export interface FilaDeDevolucion {
  productoId: string
  cajas: string
  unidades: string
  unidadesPorCaja: number | null
  nombrePresentacion: string | null
}

/**
 * D6, D9: la devolución se precarga con todo lo contado. Cada producto con contado mayor que
 * cero, en cajas y unidades si su presentación de referencia agrupa más de una unidad y solo en
 * unidades si no la hay o es de una unidad (un único campo: la cantidad no se duplica).
 */
export function precargarDevolucion(
  contados: readonly { productoId: string; contado: number }[],
  referencias: ReadonlyMap<string, ReferenciaDePresentacion>,
): FilaDeDevolucion[] {
  return contados
    .filter(({ contado }) => contado > 0)
    .map(({ productoId, contado }) => {
      const referencia = referencias.get(productoId) ?? null
      if (referencia === null || referencia.unidades <= 1) {
        return { productoId, cajas: '', unidades: String(contado), unidadesPorCaja: null, nombrePresentacion: null }
      }
      const { cajas, unidades } = desdeUnidadesBase(contado, referencia.unidades)
      return {
        productoId,
        cajas: String(cajas),
        unidades: String(unidades),
        unidadesPorCaja: referencia.unidades,
        nombrePresentacion: referencia.nombre,
      }
    })
}

/** Lo escrito en una fila de la devolución, en unidad base; `null` si no es una cantidad válida. */
export function totalDeDevolucion(fila: FilaDeDevolucion): number | null {
  const cantidad = cantidadDeLinea({ ...fila, negativa: false })
  return cantidad.ok ? cantidad.cantidadBase : null
}

export interface DevolucionDeCierre {
  ubicacion_destino_id: string
  lineas: { producto_id: string; cantidad_base: number }[]
}

export type ResultadoDeDevolucion = { ok: true; devolucion: DevolucionDeCierre | null } | { ok: false; mensaje: string }

/**
 * D6: sin destino el cierre no devuelve nada; con destino hace falta al menos una línea con
 * cantidad (las que quedaron en cero se omiten). El servidor valida el resto (que no supere
 * el saldo, que el destino sea un depósito libre).
 */
export function armarDevolucion(destinoId: string, filas: readonly FilaDeDevolucion[]): ResultadoDeDevolucion {
  if (destinoId === '') return { ok: true, devolucion: null }
  const lineas: { producto_id: string; cantidad_base: number }[] = []
  for (const fila of filas) {
    const cantidad = cantidadDeLinea({ ...fila, negativa: false })
    if (!cantidad.ok) return { ok: false, mensaje: cantidad.mensaje }
    if (cantidad.cantidadBase > 0) lineas.push({ producto_id: fila.productoId, cantidad_base: cantidad.cantidadBase })
  }
  if (lineas.length === 0) return { ok: false, mensaje: 'Indicá la cantidad que se devuelve de al menos un producto.' }
  return { ok: true, devolucion: { ubicacion_destino_id: destinoId, lineas } }
}

/** D9 (aprobado en 0.2): «Se transfieren {N} productos a {destino}.». */
export function textoDeDevolucion(productos: number, destino: string): string {
  return productos === 1
    ? `Se transfiere 1 producto a ${destino}.`
    : `Se transfieren ${String(productos)} productos a ${destino}.`
}

/** D11 (aprobado en 0.2): «Falta contar: {productos}.»; sin nombres, un texto de reserva. */
export function textoDeConteoIncompleto(nombres: readonly string[]): string {
  return nombres.length === 0 ? 'Falta contar algún producto.' : `Falta contar: ${nombres.join(', ')}.`
}

// --- Rechazos pendientes de la jornada (change 25, D9 = B; RUT-05) -----------------------------

/** D12 (aprobado en 0.2): lo que ve quien no puede resolver los rechazos. */
export const TEXTO_SIN_PERMISO_DE_REVISION = 'Las resuelve quien revisa las observaciones.'

/** `true` con una cantidad positiva; un dato que no llegó cuenta como ninguno. */
export function hayRechazosPendientes(cantidad: number | undefined): boolean {
  return cantidad !== undefined && cantidad > 0
}

/**
 * D12 (aprobado en 0.2): «Esta jornada tiene {N} operaciones rechazadas sin resolver. Hay que resolverlas antes de
 * rendir.»; con una sola, «1 operación rechazada».
 */
export function textoDeRechazosPendientes(cantidad: number): string {
  const rechazadas = cantidad === 1 ? '1 operación rechazada' : `${String(cantidad)} operaciones rechazadas`
  return `Esta jornada tiene ${rechazadas} sin resolver. Hay que resolverlas antes de rendir.`
}
