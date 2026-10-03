/**
 * Lógica pura del formulario de compra (change 11, tarea 12.1; `design.md` D1, D5, D7;
 * spec `administracion-de-compras`). Nada de esto vive en los componentes
 * (`CLAUDE.md` §5): la pantalla solo llama a estas funciones y pinta el resultado.
 *
 * El cálculo de cada línea y de los totales es `calcularLinea` / `calcularCompra` de
 * `calculoCompra.ts` (espejo del servidor, mismos casos de `cmp-02-compra.json`). Acá
 * se agrega lo propio del formulario: líneas incompletas, faltante de medios, bonificación
 * en porcentaje y armado de los cuerpos de `COMPRA_CONFIRMAR` y `COSTO_INFORMAR`.
 * Los importes nunca pasan por `number` (INV-03).
 */

import type { components } from '../../api/schema.gen'
import type { Importe } from '../../lib/money'
import { EntradaNoEsDineroExactoError, parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { calcularCompra, calcularLinea, ErrorDeCompra, type EntradaDeLinea, type LineaCalculada } from './calculoCompra'

export type Condicion = 'CONTADO' | 'CREDITO'

/** Una línea tal como la edita el usuario: textos, la bonificación en porcentaje. */
export interface LineaDeFormulario {
  productoId: string
  presentacionId: string
  cantidad: string
  valor: string
  incluyeIva: boolean
  bonificacionPorcentaje: string
}

export interface MedioDeFormulario {
  medioPagoId: string
  importe: string
  referencia: string
}

export interface FormularioDeCompra {
  proveedorId: string
  fecha: string
  ubicacionId: string
  condicion: Condicion
  numeroComprobante: string
  observacion: string
  lineas: LineaDeFormulario[]
  medios: MedioDeFormulario[]
}

/** Lo que el catálogo aporta de una línea: unidades de la presentación y alícuota del
 * producto. `null` mientras todavía no se eligió presentación o no cargó la alícuota. */
export interface ContextoDeLinea {
  unidadesPresentacion: number | null
  alicuota: string | null
}

export type VistaPreviaDeLinea =
  | { estado: 'incompleta' }
  | { estado: 'error'; codigo: string; mensaje: string }
  | { estado: 'lista'; calculada: LineaCalculada }

export interface TotalesDeVista {
  totalNeto: Importe
  ivaSugerido: Importe
  totalFacturaSugerido: Importe
}

export interface VistaPreviaDeCompra {
  lineas: VistaPreviaDeLinea[]
  /** `null` mientras alguna línea esté incompleta o con error (o no haya líneas). */
  totales: TotalesDeVista | null
}

const DECIMALES_DE_PORCENTAJE = 4 // 6 decimales de la fracción, menos los 2 del x100

/**
 * Bonificación del formulario (porcentaje, `[0, 100)`) como la fracción de seis decimales
 * que espera la API: `"10"` -> `"0.100000"`. Vacío cuenta como cero.
 */
export function porcentajeAFraccion(porcentaje: string): string {
  const texto = porcentaje.trim() === '' ? '0' : porcentaje.trim()
  let valor: Importe
  try {
    valor = parsearImporteDesdeApi(texto)
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) {
      throw new ErrorDeCompra('BONIFICACION_INVALIDA', 'La bonificación no es un porcentaje válido.')
    }
    throw error
  }
  if (valor.lt(0) || valor.gte(100) || valor.decimalPlaces() > DECIMALES_DE_PORCENTAJE) {
    throw new ErrorDeCompra(
      'BONIFICACION_INVALIDA',
      'La bonificación debe ser un porcentaje entre 0 (inclusive) y 100 (exclusive), con hasta 4 decimales.',
    )
  }
  return valor.div(100).toFixed(6)
}

function estaIncompleta(linea: LineaDeFormulario, contexto: ContextoDeLinea): boolean {
  return (
    linea.productoId === '' ||
    linea.presentacionId === '' ||
    linea.cantidad.trim() === '' ||
    linea.valor.trim() === '' ||
    contexto.unidadesPresentacion === null ||
    contexto.alicuota === null
  )
}

function entradaDeLinea(linea: LineaDeFormulario, contexto: ContextoDeLinea): EntradaDeLinea {
  return {
    unidadesPresentacion: contexto.unidadesPresentacion as number,
    cantidad: linea.cantidad.trim(),
    valor: linea.valor.trim(),
    incluyeIva: linea.incluyeIva,
    alicuota: contexto.alicuota as string,
    bonificacion: porcentajeAFraccion(linea.bonificacionPorcentaje),
  }
}

function calcularVistaDeLinea(linea: LineaDeFormulario, contexto: ContextoDeLinea): VistaPreviaDeLinea {
  if (estaIncompleta(linea, contexto)) return { estado: 'incompleta' }
  try {
    return { estado: 'lista', calculada: calcularLinea(entradaDeLinea(linea, contexto)) }
  } catch (error) {
    if (error instanceof ErrorDeCompra) {
      return { estado: 'error', codigo: error.codigo, mensaje: error.message }
    }
    throw error
  }
}

/**
 * Vista previa por línea y en total (CMP-02): cada línea se calcula por separado, así un
 * error en una no esconde el resultado de las otras; los totales (neto, IVA sugerido y
 * total de factura sugerido, D1) solo existen cuando todas las líneas están listas.
 * `contextos[i]` es el del catálogo para `lineas[i]`.
 */
export function calcularVistaPrevia(
  lineas: readonly LineaDeFormulario[],
  contextos: readonly ContextoDeLinea[],
): VistaPreviaDeCompra {
  const vistas = lineas.map((linea, indice) =>
    calcularVistaDeLinea(linea, contextos[indice] ?? { unidadesPresentacion: null, alicuota: null }),
  )
  const todasListas = vistas.length > 0 && vistas.every((vista) => vista.estado === 'lista')
  if (!todasListas) return { lineas: vistas, totales: null }

  const entradas = lineas.map((linea, indice) => entradaDeLinea(linea, contextos[indice] as ContextoDeLinea))
  try {
    const totales = calcularCompra(entradas)
    return {
      lineas: vistas,
      totales: {
        totalNeto: totales.totalNeto,
        totalFacturaSugerido: totales.totalFacturaSugerido,
        ivaSugerido: redondearImporte(totales.totalFacturaSugerido.sub(totales.totalNeto)),
      },
    }
  } catch (error) {
    if (error instanceof ErrorDeCompra) return { lineas: vistas, totales: null }
    throw error
  }
}

function importeOCero(texto: string): Importe {
  try {
    return parsearImporteDesdeApi(texto.trim())
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) return parsearImporteDesdeApi('0')
    throw error
  }
}

/**
 * Lo que falta (positivo) o sobra (negativo) para que los medios de una compra de
 * contado sumen el total de factura (INV-08, TR-10). Un importe vacío o inválido cuenta
 * como cero: el servidor valida igual.
 */
export function calcularFaltanteDeMedios(totalFactura: string, medios: readonly MedioDeFormulario[]): Importe {
  const suma = medios.reduce((acumulado, medio) => acumulado.add(importeOCero(medio.importe)), parsearImporteDesdeApi('0'))
  return redondearImporte(importeOCero(totalFactura).sub(suma))
}

function textoONulo(texto: string): string | null {
  const recortado = texto.trim()
  return recortado === '' ? null : recortado
}

/**
 * Cuerpo de `COMPRA_CONFIRMAR` (`POST /compras`). `totalFactura` es el total editable ya
 * resuelto (el sugerido o el que cargó el usuario); los importes viajan como string con
 * dos decimales (INV-03). A crédito no se envían medios (CMP-03).
 */
export function construirSolicitudDeCompra(
  formulario: FormularioDeCompra,
  totalFactura: string,
): components['schemas']['CompraConfirmarRequest'] {
  const medios =
    formulario.condicion === 'CONTADO'
      ? formulario.medios.map((medio) => ({
          medio_pago_id: medio.medioPagoId,
          importe: redondearImporte(medio.importe.trim()).toFixed(2),
          referencia: textoONulo(medio.referencia),
        }))
      : []
  return {
    proveedor_id: formulario.proveedorId,
    fecha: formulario.fecha,
    ubicacion_id: formulario.ubicacionId,
    condicion: formulario.condicion,
    total_factura: redondearImporte(totalFactura.trim()).toFixed(2),
    numero_comprobante: textoONulo(formulario.numeroComprobante),
    observacion: textoONulo(formulario.observacion),
    lineas: formulario.lineas.map((linea) => ({
      producto_id: linea.productoId,
      presentacion_id: linea.presentacionId,
      cantidad: linea.cantidad.trim(),
      valor: redondearImporte(linea.valor.trim()).toFixed(2),
      incluye_iva: linea.incluyeIva,
      bonificacion: porcentajeAFraccion(linea.bonificacionPorcentaje),
    })),
    medios,
  }
}

/**
 * Un costo del lote de `COSTO_INFORMAR` a partir de una línea de la compra (CMP-04, D7):
 * presentación, valor, IVA y bonificación de la línea, con vigencia desde la fecha de la
 * compra. Solo se envía si el usuario lo pide explícitamente.
 */
export function construirCostoInformar(
  linea: LineaDeFormulario,
  fechaDeCompra: string,
): components['schemas']['CostoDelLoteRequest'] {
  return {
    producto_id: linea.productoId,
    presentacion_id: linea.presentacionId,
    valor: redondearImporte(linea.valor.trim()).toFixed(2),
    incluye_iva: linea.incluyeIva,
    bonificacion: porcentajeAFraccion(linea.bonificacionPorcentaje),
    vigencia_desde: fechaDeCompra,
  }
}

/** Presentación de un producto tal como la devuelve el catálogo (solo lo que se usa). */
export interface PresentacionDeCatalogo {
  id: string
  nombre: string
  unidades_base: number
  activo: boolean
  usar_en_compra: boolean
}

/** Solo las presentaciones activas y de compra se ofrecen en una línea de compra. */
export function presentacionesDeCompra<T extends PresentacionDeCatalogo>(
  presentaciones: readonly T[] | undefined,
): T[] {
  return (presentaciones ?? []).filter((presentacion) => presentacion.activo && presentacion.usar_en_compra)
}

/** Unidades de la presentación elegida y alícuota del producto para calcular una línea. */
export function contextoDeLinea(
  producto: { alicuota_id: string; presentaciones: readonly PresentacionDeCatalogo[] } | undefined,
  presentacionId: string,
  alicuotas: readonly { id: string; valor: string }[],
): ContextoDeLinea {
  if (producto === undefined) return { unidadesPresentacion: null, alicuota: null }
  const presentacion = producto.presentaciones.find((p) => p.id === presentacionId)
  const alicuota = alicuotas.find((a) => a.id === producto.alicuota_id)
  return {
    unidadesPresentacion: presentacion?.unidades_base ?? null,
    alicuota: alicuota?.valor ?? null,
  }
}

export interface EntradaDeConfirmacion {
  formulario: FormularioDeCompra
  vistaPrevia: VistaPreviaDeCompra
  /** Total de factura ya resuelto (el sugerido o el que cargó el usuario). */
  totalFactura: string
  /** Ids de los medios de pago que exigen referencia. */
  mediosRequierenReferencia: ReadonlySet<string>
}

/**
 * Si el formulario está en condiciones de enviarse (el servidor valida igual, TR-10):
 * datos de cabecera, todas las líneas calculadas, total de factura positivo y, de contado,
 * medios completos que suman exactamente el total (INV-08).
 */
export function puedeConfirmar(entrada: EntradaDeConfirmacion): boolean {
  const { formulario, vistaPrevia, totalFactura } = entrada
  if (formulario.proveedorId === '' || formulario.ubicacionId === '' || formulario.fecha === '') return false
  if (vistaPrevia.totales === null) return false

  let total: Importe
  try {
    total = parsearImporteDesdeApi(totalFactura.trim())
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) return false
    throw error
  }
  if (total.lte(0)) return false

  if (formulario.condicion === 'CREDITO') return true
  if (formulario.medios.length === 0) return false
  const mediosCompletos = formulario.medios.every(
    (medio) =>
      medio.medioPagoId !== '' &&
      importeOCero(medio.importe).gt(0) &&
      (!entrada.mediosRequierenReferencia.has(medio.medioPagoId) || medio.referencia.trim() !== ''),
  )
  return mediosCompletos && calcularFaltanteDeMedios(totalFactura, formulario.medios).isZero()
}
