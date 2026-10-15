/**
 * Presentación de una regla de descuento y acciones que ofrece según su estado (DSC-01, DSC-03,
 * DSC-04; `01` §18; `design.md` D15, D16 del change 16). Solo texto y decisiones de la interfaz,
 * sin lógica de negocio nueva: el servidor valida y autoriza igual (SEG-06). Los importes y
 * porcentajes se tratan como cadenas exactas y decimal.js; nunca pasan por `number` (INV-03).
 */

import { formatearFechaHora } from '../../lib/fecha'
import { formatearImporte, formatearPorcentaje, parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { sinCerosFinales } from '../precios/decimales'

export interface AlcancePresentable {
  tipo: string
  entidad_id: string
  nombre: string
}

/** Lo que la descripción necesita de una regla (la respuesta de la API la cumple). */
export interface ReglaPresentable {
  tipo: string
  medida: string
  operador: string
  umbral: string
  accion_tipo: string
  accion_porcentaje: string | null
  accion_importe: string | null
  prioridad: number
  acumulable: boolean
  vigencia_desde: string | null
  vigencia_hasta: string | null
  estado: string
  alcances: readonly AlcancePresentable[]
}

export interface DescripcionDeRegla {
  /** "Cajas equivalentes ≥ 20 → 5 %" */
  resumen: string
  alcance: string
  acumulable: string
  prioridad: string
}

const ETIQUETA_DE_MEDIDA: Record<string, string> = {
  CAJAS_EQUIVALENTES: 'Cajas equivalentes',
  UNIDADES_BASE: 'Unidades base',
  IMPORTE_BRUTO: 'Importe bruto',
}

const SIMBOLO_DE_OPERADOR: Record<string, string> = { GTE: '≥', GT: '>' }

const ETIQUETA_DE_ALCANCE: Record<string, string> = {
  PRODUCTO: 'Producto',
  CATEGORIA: 'Categoría',
  MARCA: 'Marca',
}

const ETIQUETA_DE_ESTADO: Record<string, string> = {
  BORRADOR: 'Borrador',
  ACTIVA: 'Activa',
  PAUSADA: 'Pausada',
  VENCIDA: 'Vencida',
}

/** Estados que filtra el listado (`VENCIDA` es derivado: lo calcula el servidor). */
export const ESTADOS_DE_REGLA: readonly string[] = ['BORRADOR', 'ACTIVA', 'PAUSADA', 'VENCIDA']

export const PERMISO_GESTIONAR_DESCUENTOS = 'GESTIONAR_DESCUENTOS'

export function etiquetaDeEstadoDeRegla(estado: string): string {
  return ETIQUETA_DE_ESTADO[estado] ?? estado
}

export function etiquetaDeMedida(medida: string): string {
  return ETIQUETA_DE_MEDIDA[medida] ?? medida
}

export function etiquetaDeTipoDeAlcance(tipo: string): string {
  return ETIQUETA_DE_ALCANCE[tipo] ?? tipo
}

/** Coma decimal (es-AR) y sin ceros de relleno: `"0.5000"` -> `"0,5"`, `"20.0000"` -> `"20"`. */
function numeroSinRelleno(valor: string): string {
  return sinCerosFinales(valor).replace('.', ',')
}

function textoDelImporte(valor: string): string {
  return `$ ${formatearImporte(redondearImporte(valor))}`
}

function textoDelUmbral(medida: string, umbral: string): string {
  return medida === 'IMPORTE_BRUTO' ? textoDelImporte(umbral) : numeroSinRelleno(umbral)
}

function textoDeLaAccion(regla: ReglaPresentable): string {
  if (regla.accion_tipo === 'IMPORTE_FIJO' && regla.accion_importe !== null) {
    return `${textoDelImporte(regla.accion_importe)} fijos`
  }
  if (regla.accion_porcentaje !== null) {
    return formatearPorcentaje(parsearImporteDesdeApi(regla.accion_porcentaje))
  }
  return ''
}

/** Condición, acción, alcance, acumulabilidad y prioridad de una regla, listos para mostrar. */
export function describirRegla(regla: ReglaPresentable): DescripcionDeRegla {
  const condicion = `${etiquetaDeMedida(regla.medida)} ${SIMBOLO_DE_OPERADOR[regla.operador] ?? regla.operador} ${textoDelUmbral(regla.medida, regla.umbral)}`
  const alcance =
    regla.alcances.length === 0
      ? 'Sobre toda la venta'
      : `Sobre ${regla.alcances.map((a) => `${etiquetaDeTipoDeAlcance(a.tipo)} ${a.nombre}`).join(', ')}`
  return {
    resumen: `${condicion} → ${textoDeLaAccion(regla)}`,
    alcance,
    acumulable: regla.acumulable ? 'Acumulable' : 'No acumulable',
    prioridad: `Prioridad ${regla.prioridad}`,
  }
}

/** "Desde … hasta …", solo una de las dos, o "Sin vigencia definida" (D16). */
export function describirVigencia(desde: string | null, hasta: string | null): string {
  if (desde !== null && hasta !== null) return `Desde ${formatearFechaHora(desde)} hasta ${formatearFechaHora(hasta)}`
  if (desde !== null) return `Desde ${formatearFechaHora(desde)}`
  if (hasta !== null) return `Hasta ${formatearFechaHora(hasta)}`
  return 'Sin vigencia definida'
}

export interface AccionesDeRegla {
  editar: boolean
  activar: boolean
  pausar: boolean
  /** Fijar la vigencia hasta de una regla ya activada (D15, D16). */
  ponerFin: boolean
}

/**
 * Qué ofrece la pantalla según el estado y los permisos (`01` §18; D15): editar solo un borrador;
 * activar un borrador o una pausada; pausar una activa; poner fin a una activa o pausada. Una
 * `VENCIDA` es de solo lectura. Ocultar es una comodidad: el servidor valida igual (SEG-06).
 */
export function accionesDeRegla(estado: string, permisos: readonly string[]): AccionesDeRegla {
  if (!permisos.includes(PERMISO_GESTIONAR_DESCUENTOS)) {
    return { editar: false, activar: false, pausar: false, ponerFin: false }
  }
  return {
    editar: estado === 'BORRADOR',
    activar: estado === 'BORRADOR' || estado === 'PAUSADA',
    pausar: estado === 'ACTIVA',
    ponerFin: estado === 'ACTIVA' || estado === 'PAUSADA',
  }
}
