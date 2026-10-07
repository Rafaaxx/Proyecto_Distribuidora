import { calcularBrutoDeLinea } from './brutoDeLinea'
import { formatearImporte } from '../../lib/money'
import { aImporte, esDecimalNoNegativo, normalizarDecimal, sinCerosFinales } from './decimales'
import { ETIQUETA_DE_DIRECCION, type DireccionRedondeo } from './listaSchema'
import { fraccionDesdePorcentaje } from './reglaSchema'

/**
 * Textos y cálculo de presentación de las pantallas de precios (change 13, tarea 12.1).
 * Sin lógica de negocio nueva: la fórmula es PRC-12, el precio por presentación es PRC-22
 * (`brutoDeLinea.ts`) y los estados derivados los calcula el servidor (PRC-03).
 */

/** Factor de la fórmula con coma decimal y al menos dos decimales (`1,30`, `0,875`). */
function formatearFactor(factor: string): string {
  const recortado = sinCerosFinales(factor)
  const [entero = '0', decimales = ''] = recortado.split('.')
  return `${entero},${decimales.padEnd(2, '0')}`
}

/** PRC-12: la fórmula de una regla (`valor` es la fracción de la API, `"0.300000"`). */
export function textoDeFormula(tipo: string, valor: string): string {
  const m = aImporte(valor)
  if (tipo === 'MARKUP') return `Precio = costo × ${formatearFactor(m.plus(1).toFixed(6))}`
  if (tipo === 'MARGEN_BRUTO') return `Precio = costo ÷ ${formatearFactor(aImporte('1').minus(m).toFixed(6))}`
  return ''
}

/**
 * PRC-22: precio de una presentación de `unidadesDePresentacion` unidades base a partir del
 * precio de referencia (string) y sus unidades de referencia. Es solo para mostrar: nunca
 * arma un total.
 */
export function precioPorPresentacion(
  precioReferencia: string,
  unidadesReferencia: number,
  unidadesDePresentacion: number,
): string {
  return calcularBrutoDeLinea(precioReferencia, unidadesReferencia, unidadesDePresentacion).toFixed(2)
}

const ETIQUETA_DE_ESTADO: Record<string, string> = {
  BORRADOR: 'Borrador',
  PUBLICADA: 'Publicada',
  ANULADA: 'Anulada',
  PROGRAMADA: 'Programada',
  VIGENTE: 'Vigente',
  HISTORICA: 'Histórica',
}

/** El estado derivado (PRC-03) manda sobre el almacenado cuando existe. */
export function etiquetaDeEstadoDeVersion(estado: string, estadoDerivado: string | null): string {
  const clave = estadoDerivado ?? estado
  return ETIQUETA_DE_ESTADO[clave] ?? clave
}

/** PRC-05: solo se anula una versión publicada cuya vigencia aún no comenzó. */
export function puedeAnularse(estado: string, estadoDerivado: string | null): boolean {
  return estado === 'PUBLICADA' && estadoDerivado === 'PROGRAMADA'
}

const ETIQUETA_DE_RELACION: Record<string, string> = { NUEVO: 'Nuevo', CAMBIA: 'Cambia', IGUAL: 'Igual' }

export function etiquetaDeRelacion(relacion: string | null): string {
  return relacion === null ? '' : (ETIQUETA_DE_RELACION[relacion] ?? relacion)
}

const ETIQUETA_DE_TIPO_DE_MARGEN: Record<string, string> = { MARKUP: 'Markup', MARGEN_BRUTO: 'Margen bruto' }

export function etiquetaDeTipoDeMargen(tipo: string): string {
  return ETIQUETA_DE_TIPO_DE_MARGEN[tipo] ?? tipo
}

export const ETIQUETA_DE_CAUSA_SIN_PRECIO: Record<string, string> = {
  SIN_COSTO: 'Sin costo informado vigente',
  SIN_REGLA: 'Sin regla de margen aplicable',
  PRECIO_NO_POSITIVO: 'El redondeo deja el precio en cero',
  SIN_PRESENTACION_DE_REFERENCIA: 'Sin presentación de referencia',
  SIN_CALCULAR: 'Se podría calcular hoy: regenerá el borrador',
}

export function etiquetaDeCausaSinPrecio(causa: string): string {
  return ETIQUETA_DE_CAUSA_SIN_PRECIO[causa] ?? causa
}

export interface SenalesDePrecio {
  sin_costo: boolean
  margen_menor: boolean
  costo_otra_regla_iva: boolean
  costos_distintos_por_presentacion: boolean
}

/** Los rótulos de las señales que valen en un precio del borrador (D2, D3, D7). */
export function etiquetasDeSenales(senales: SenalesDePrecio | null): string[] {
  if (senales === null) return []
  const etiquetas: string[] = []
  if (senales.sin_costo) etiquetas.push('Sin costo')
  if (senales.margen_menor) etiquetas.push('Margen menor que el de la regla')
  if (senales.costo_otra_regla_iva) etiquetas.push('Costo calculado con otra regla de IVA')
  if (senales.costos_distintos_por_presentacion) etiquetas.push('Los costos por presentación difieren')
  return etiquetas
}

/** `"100.00"` + `ARRIBA` -> `100,00 · Hacia arriba` (múltiplo y dirección de un redondeo, PRC-14). */
export function descripcionDeRedondeo(multiplo: string, direccion: string): string {
  const texto = ETIQUETA_DE_DIRECCION[direccion as DireccionRedondeo] ?? direccion
  return `${formatearImporte(aImporte(multiplo))} · ${texto}`
}

const ETIQUETA_DE_ALCANCE: Record<string, string> = {
  LISTA: 'Toda la lista',
  CATEGORIA: 'Categoría',
  MARCA: 'Marca',
  PRODUCTO: 'Producto',
  PROVEEDOR: 'Proveedor',
}

export function etiquetaDeAlcance(alcance: string): string {
  return ETIQUETA_DE_ALCANCE[alcance] ?? alcance
}

/**
 * La fórmula (PRC-12) con el porcentaje tal como la persona lo escribe (`"12,5"`); vacío si el
 * valor todavía no es válido para ese tipo (un margen bruto de 100% o más no tiene fórmula).
 */
export function formulaDesdePorcentaje(tipo: string, porcentaje: string): string {
  const texto = normalizarDecimal(porcentaje)
  if (!esDecimalNoNegativo(texto, 4)) return ''
  if (tipo === 'MARGEN_BRUTO' && aImporte(texto).gte(100)) return ''
  return textoDeFormula(tipo, fraccionDesdePorcentaje(texto))
}

function plural(cantidad: number, singular: string, plural: string): string {
  if (cantidad === 0) return `ningún ${singular}`
  return cantidad === 1 ? `1 ${singular}` : `${cantidad} ${plural}`
}

/** Texto de la confirmación de publicar: `"98 precios, 2 productos sin precio"`. */
export function resumenDePublicacion(precios: number, productosSinPrecio: number): string {
  return `${plural(precios, 'precio', 'precios')}, ${plural(productosSinPrecio, 'producto', 'productos')} sin precio`
}

/** Avisos del resultado de generar el borrador: cuántos precios llevan las señales de costo (D2, D3). */
export function avisosDeGeneracion(generacion: {
  precios_con_otra_regla_iva: number
  precios_con_costos_distintos: number
}): string[] {
  const avisos: string[] = []
  const { precios_con_otra_regla_iva: iva, precios_con_costos_distintos: distintos } = generacion
  if (iva > 0) avisos.push(`${iva} ${iva === 1 ? 'precio calculado' : 'precios calculados'} con otra regla de IVA`)
  if (distintos > 0) {
    avisos.push(`${distintos} ${distintos === 1 ? 'precio' : 'precios'} con costos distintos por presentación`)
  }
  return avisos
}
