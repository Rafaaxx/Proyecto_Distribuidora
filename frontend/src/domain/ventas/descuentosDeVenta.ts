/**
 * Descuentos de la pantalla de venta (change 18b, tarea 13.1; DSC-05, DSC-06, DSC-07, DSC-08,
 * INV-03; `design.md` D11, D15, D20). Lógica pura: lee los porcentajes que escribe el usuario,
 * dice cuál rige en cada línea, cuál es el mayor manual, si hace falta autorización con el tope del
 * contexto y arma los descuentos que se envían. Ningún importe pasa por `number`: todo con
 * `decimal.js` desde `lib/money.ts`. El servidor valida igual (TR-10).
 */

import type { Importe } from '../../lib/money'
import { formatearPorcentaje, parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { ErrorDeDescuentos } from '../descuentos/errores'
import { calcularDescuentos } from '../descuentos/motor'
import type { AccionTipo, LineaVenta, Medida, Operador, ReglaDescuento, TipoAlcance, TipoRegla } from '../descuentos/tipos'
import {
  evaluarDescuentoManual,
  PERMISO_AUTORIZAR_DESCUENTO,
  PERMISO_DESCUENTO_MANUAL,
} from '../descuentos/manual'

const PORCENTAJE_ESCRITO = /^\d+([.,]\d{1,4})?$/
const MENSAJE_DE_PORCENTAJE_INVALIDO =
  'Ingresá un porcentaje mayor que 0 y hasta 100, con hasta 4 decimales.'

export type ResultadoDePorcentaje =
  | { valido: true; fraccion: string | null }
  | { valido: false; mensaje: string }

/**
 * Lo que el usuario escribió (`"7,5"` = 7,5 %) como fracción de texto con seis decimales
 * (`"0.075000"`). Vacío es "sin porcentaje", no un error. Mayor que 0 y hasta 100 (DSC-06); no se
 * puede poner 0 % para dejar un producto sin el general (DSC-05).
 */
export function leerPorcentaje(texto: string): ResultadoDePorcentaje {
  const recortado = texto.trim()
  if (recortado === '') return { valido: true, fraccion: null }
  if (!PORCENTAJE_ESCRITO.test(recortado)) return { valido: false, mensaje: MENSAJE_DE_PORCENTAJE_INVALIDO }
  const puntos = parsearImporteDesdeApi(recortado.replace(',', '.'))
  if (puntos.lessThanOrEqualTo(0) || puntos.greaterThan(100)) {
    return { valido: false, mensaje: MENSAJE_DE_PORCENTAJE_INVALIDO }
  }
  return { valido: true, fraccion: puntos.dividedBy(100).toFixed(6) }
}

export type OrigenDelPorcentaje = 'propio' | 'general'

export interface PorcentajeQueRige {
  fraccion: string | null
  origen: OrigenDelPorcentaje | null
}

/** DSC-05, DSC-08: el propio de la línea reemplaza al general, sea mayor o menor. */
export function porcentajeQueRige(general: string | null, propio: string | null): PorcentajeQueRige {
  if (propio !== null) return { fraccion: propio, origen: 'propio' }
  if (general !== null) return { fraccion: general, origen: 'general' }
  return { fraccion: null, origen: null }
}

/** `"10 % (propio)"`, `"7,5 % (general)"` o vacío. */
export function textoDePorcentajeQueRige(rige: PorcentajeQueRige): string {
  if (rige.fraccion === null || rige.origen === null) return ''
  return `${formatearPorcentaje(parsearImporteDesdeApi(rige.fraccion))} (${rige.origen})`
}

/** El mayor porcentaje manual que quedó en alguna línea (DSC-06); nulo si ninguna lleva. */
export function mayorPorcentajeManual(fracciones: readonly (string | null)[]): string | null {
  let mayor: string | null = null
  for (const fraccion of fracciones) {
    if (fraccion === null) continue
    if (mayor === null || parsearImporteDesdeApi(fraccion).greaterThan(parsearImporteDesdeApi(mayor))) {
      mayor = fraccion
    }
  }
  return mayor
}

/** Lo que dice `GET /ventas/contexto` del descuento manual (`tope` como fracción de texto). */
export interface ContextoDeDescuento {
  habilitado: boolean
  motivoObligatorio: boolean
  tienePermiso: boolean
  tope: string | null
  puedeAutorizar: boolean
}

export type NecesidadDeDescuento =
  | { estado: 'sin-descuento' }
  | { estado: 'deshabilitado' }
  | { estado: 'sin-permiso' }
  | { estado: 'dentro-del-tope'; tope: string }
  | { estado: 'permiso-propio'; tope: string }
  | { estado: 'requiere-autorizador'; tope: string }

/**
 * DSC-06 con la gemela `evaluarDescuentoManual` (una sola vez por venta, con el mayor manual).
 * El motivo se revisa aparte (`motivoFalta`): acá se le pasa uno para que no tape lo demás.
 */
export function necesidadDeAutorizacionDeDescuento(
  mayorManual: string | null,
  contexto: ContextoDeDescuento,
): NecesidadDeDescuento {
  if (mayorManual === null) return { estado: 'sin-descuento' }
  const permisosUsuario = [
    ...(contexto.tienePermiso ? [PERMISO_DESCUENTO_MANUAL] : []),
    ...(contexto.puedeAutorizar ? [PERMISO_AUTORIZAR_DESCUENTO] : []),
  ]
  const tope = contexto.tope ?? '0'
  try {
    const resultado = evaluarDescuentoManual({
      usuarioId: 'yo',
      descuentoManualHabilitado: contexto.habilitado,
      motivoObligatorio: null,
      permisosUsuario,
      topeRol: tope,
      topePropio: null,
      porcentajeMaximo: mayorManual,
      motivo: null,
      autorizador: null,
    })
    return resultado.resolucion === 'DENTRO_DEL_TOPE'
      ? { estado: 'dentro-del-tope', tope }
      : { estado: 'permiso-propio', tope }
  } catch (error) {
    if (!(error instanceof ErrorDeDescuentos)) throw error
    if (error.codigo === 'DESCUENTO_MANUAL_DESHABILITADO') return { estado: 'deshabilitado' }
    if (error.codigo === 'PERMISO_REQUERIDO') return { estado: 'sin-permiso' }
    if (error.codigo === 'AUTORIZACION_REQUERIDA') return { estado: 'requiere-autorizador', tope }
    throw error
  }
}

/** El aviso del tope que ve quien vende (D15). */
export function avisoDeTope(contexto: ContextoDeDescuento): string {
  if (!contexto.habilitado) return 'La empresa no permite descuentos manuales por ahora.'
  if (!contexto.tienePermiso || contexto.tope === null) return 'No podés dar descuentos manuales.'
  const tope = parsearImporteDesdeApi(contexto.tope)
  const hasta = `Podés descontar hasta ${formatearPorcentaje(tope)}`
  if (tope.greaterThanOrEqualTo(1)) return `${hasta}.`
  return contexto.puedeAutorizar
    ? `${hasta}; más lo autorizás vos con tu permiso.`
    : `${hasta}; más pide autorización.`
}

/** Falta el motivo: la organización lo exige, hay descuento manual y no se eligió ninguno (DSC-06). */
export function motivoFalta(
  mayorManual: string | null,
  contexto: ContextoDeDescuento,
  motivoId: string,
): boolean {
  return mayorManual !== null && contexto.motivoObligatorio && motivoId.trim() === ''
}

// --- el pedido con descuentos -----------------------------------------------------------------

export type OrigenDeDescuento = 'AUTOMATICO' | 'MANUAL'

/** Un descuento de una línea tal como se envía (DSC-08): `reglaId` nulo en el manual. */
export interface DescuentoDeLinea {
  origen: OrigenDeDescuento
  reglaId: string | null
  porcentaje: string | null
  importe: string
}

/** Lo que la gemela del motor necesita de una línea además del bruto (DSC-05, ADR-050). */
export interface DatosParaElMotor {
  cantidadBase: number
  unidadesReferencia: number
  productoId: string
  categoriaId: string
  marcaId: string
}

export interface EntradaDeLinea {
  lineaId: string
  bruto: string
  /** Fracción propia de la línea o nulo. */
  propio: string | null
  /** Si viene en todas las líneas y se pasan reglas, los automáticos se calculan con el motor. */
  motor?: DatosParaElMotor
}

/** Una regla de `GET /ventas/descuentos-aplicables`, tal como llega (snake_case, importes en texto). */
export interface ReglaDeApi {
  id: string
  tipo: string
  medida: string
  operador: string
  umbral: string
  accion_tipo: string
  accion_porcentaje: string | null
  accion_importe: string | null
  acumulable: boolean
  prioridad: number
  alcances: readonly { tipo: string; entidad_id: string }[]
}

/** La regla de la API como la espera el motor; el servidor ya validó los valores (TR-10). */
export function reglaDelMotorDesdeApi(regla: ReglaDeApi): ReglaDescuento {
  return {
    id: regla.id,
    tipo: regla.tipo as TipoRegla,
    medida: regla.medida as Medida,
    operador: regla.operador as Operador,
    umbral: regla.umbral,
    accionTipo: regla.accion_tipo as AccionTipo,
    accionPorcentaje: regla.accion_porcentaje,
    accionImporte: regla.accion_importe,
    acumulable: regla.acumulable,
    prioridad: regla.prioridad,
    alcances: regla.alcances.map((a) => ({ tipo: a.tipo as TipoAlcance, entidadId: a.entidad_id })),
  }
}

export interface LineaConDescuentos {
  lineaId: string
  descuentos: DescuentoDeLinea[]
  descuentoTotal: string
  neto: string
  rige: PorcentajeQueRige
}

export interface PedidoConDescuentos {
  lineas: LineaConDescuentos[]
  total: string
  mayorManual: string | null
}

/**
 * Descuentos y neto de cada línea y total (DSC-05, DSC-07, INV-14). Si el servidor ya resolvió los
 * descuentos de una línea (`conocidos`, de un `DESCUENTO_DIFIERE` aceptado) se usan tal cual;
 * si no, se calcula solo el manual, redondeado línea por línea con mitad hacia arriba, sobre el
 * bruto: los automáticos los resuelve el servidor y vuelven en ese aviso (D11).
 */
export function aplicarDescuentosAlPedido(
  lineas: readonly EntradaDeLinea[],
  general: string | null,
  conocidos: ReadonlyMap<string, readonly DescuentoDeLinea[]> | null,
  reglas?: readonly ReglaDescuento[],
): PedidoConDescuentos {
  const cero = redondearImporte('0')
  let total: Importe = cero
  const delMotor = descuentosConElMotor(lineas, general, reglas)
  const resultado = lineas.map((linea): LineaConDescuentos => {
    const rige = porcentajeQueRige(general, linea.propio)
    const bruto = parsearImporteDesdeApi(linea.bruto)
    const delServidor = conocidos?.get(linea.lineaId)
    let descuentos: DescuentoDeLinea[]
    if (delServidor !== undefined) {
      descuentos = [...delServidor]
    } else if (delMotor?.has(linea.lineaId)) {
      descuentos = [...(delMotor.get(linea.lineaId) as DescuentoDeLinea[])]
    } else {
      descuentos = []
      if (rige.fraccion !== null) {
        const importe = redondearImporte(bruto.times(parsearImporteDesdeApi(rige.fraccion)))
        if (importe.greaterThan(0)) {
          descuentos.push({ origen: 'MANUAL', reglaId: null, porcentaje: rige.fraccion, importe: importe.toFixed(2) })
        }
      }
    }
    const descuentoTotal = descuentos.reduce((suma, d) => suma.plus(parsearImporteDesdeApi(d.importe)), cero)
    const neto = redondearImporte(bruto.minus(descuentoTotal))
    total = total.plus(neto)
    return { lineaId: linea.lineaId, descuentos, descuentoTotal: descuentoTotal.toFixed(2), neto: neto.toFixed(2), rige }
  })
  const mayorManual = mayorPorcentajeManual(
    resultado.flatMap((l) => l.descuentos.filter((d) => d.origen === 'MANUAL').map((d) => d.porcentaje)),
  )
  return { lineas: resultado, total: redondearImporte(total).toFixed(2), mayorManual }
}

/**
 * Automáticos y manuales de todas las líneas con la gemela del motor (DSC-05, ADR-050); nulo si
 * no se pasaron reglas, si falta algún dato de línea o si el motor rechaza la entrada (entonces
 * la pantalla sigue con el manual solo y el servidor decide).
 */
function descuentosConElMotor(
  lineas: readonly EntradaDeLinea[],
  general: string | null,
  reglas: readonly ReglaDescuento[] | undefined,
): Map<string, DescuentoDeLinea[]> | null {
  if (reglas === undefined || lineas.length === 0) return null
  const paraElMotor: LineaVenta[] = []
  for (const linea of lineas) {
    if (linea.motor === undefined) return null
    paraElMotor.push({ id: linea.lineaId, bruto: linea.bruto, descuentoManual: linea.propio, ...linea.motor })
  }
  try {
    const resultado = calcularDescuentos(paraElMotor, reglas, general)
    return new Map(
      resultado.lineas.map((linea) => [
        linea.id,
        linea.descuentos.map(
          (d): DescuentoDeLinea => ({
            origen: d.origen,
            reglaId: d.reglaId,
            porcentaje: d.porcentaje === null ? null : d.porcentaje.toFixed(6),
            importe: d.importe.toFixed(2),
          }),
        ),
      ]),
    )
  } catch (error) {
    if (error instanceof ErrorDeDescuentos) return null
    throw error
  }
}
