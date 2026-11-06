/**
 * Etiqueta y detalle legible de cada observación de la bandeja de `/admin/revision` (change 25, tarea 13.1;
 * D3, D12; SYN-07, DSC-09, CRE-09). Lógica pura, sin React: los importes llegan como string de la API y se
 * calculan con `decimal.js` y se muestran con `lib/money.ts` (INV-03). La bandeja devuelve el detalle crudo de
 * cada código; acá se traduce. Un código o un detalle que no se conoce nunca falla: el código se muestra tal cual.
 */

import { formatearFechaHora } from '../../lib/fecha'
import { formatearPorcentaje, parsearImporteDesdeApi } from '../../lib/money'
import { formatearMonto } from '../cuentas-corrientes/presentacion'
import { formatearCantidad } from '../stock/cantidades'

const ETIQUETAS_DE_OBSERVACION: Record<string, string> = {
  STOCK_NEGATIVO: 'Stock negativo',
  VENTA_SIN_COSTO: 'Venta sin costo',
  JORNADA_LIBERADA: 'Jornada liberada',
  LISTA_NO_VIGENTE: 'Lista no vigente',
  PERMISO_REVOCADO: 'Permiso revocado',
  CLIENTE_NO_HABILITADO: 'Cliente no habilitado',
  CONSUMIDOR_FINAL_CON_DEUDA: 'Consumidor final con deuda',
  MEDIO_INACTIVO: 'Medio de pago inactivo',
  REFERENCIA_FALTANTE: 'Falta la referencia',
  // Change 18b (D9): los mismos títulos del tema de ayuda "avisos de las ventas".
  DESCUENTO_DIFIERE: 'Descuentos distintos',
  AUTORIZACION_OFFLINE: 'Autorización sin señal',
  EXCESO_CREDITO_ADVERTIDO: 'Exceso de crédito advertido',
  EXCESO_CREDITO_AUTORIZADO_OFFLINE: 'Exceso dentro de la tolerancia',
  EXCESO_CREDITO_DETECTADO_SYNC: 'Exceso de crédito detectado al sincronizar',
  // Change 25 (D12): las que faltaban.
  UBICACION_TOMADA_AL_SINCRONIZAR: 'Ubicación tomada al sincronizar',
  JORNADA_RENDIDA: 'Llegó después de la rendición',
  PRODUCTO_DESACTIVADO: 'Producto desactivado',
}

/** Los códigos de SYN-07 por los que se filtra la bandeja (el catálogo del servidor). */
export const CODIGOS_DE_OBSERVACION: readonly string[] = [
  ...Object.keys(ETIQUETAS_DE_OBSERVACION),
  'ANULACION_COMPRA_SIN_RECALCULO',
]

/** La etiqueta del código; uno que no se conoce se muestra tal cual. */
export function etiquetaDeObservacion(codigo: string): string {
  return ETIQUETAS_DE_OBSERVACION[codigo] ?? codigo
}

/** Nombres que la pantalla conoce, por id. Lo que falta se omite del texto, no se inventa. */
export interface NombresDeRevision {
  usuarios?: ReadonlyMap<string, string>
  productos?: ReadonlyMap<string, string>
  /** Número de línea (desde 1) por `linea_id`. */
  lineas?: ReadonlyMap<string, number>
  /** Vendedor de la jornada que tenía la ubicación (`UBICACION_TOMADA_AL_SINCRONIZAR`). */
  vendedorDeJornada?: string
}

/** Los nombres que el servidor manda junto a cada aviso de la bandeja (campos opcionales; `null` si no aplican). */
export interface NombresDelServidor {
  autorizador?: string | null
  producto?: string | null
  linea?: number | null
  vendedor_de_jornada?: string | null
}

/**
 * Los nombres de un aviso a partir de lo que manda el servidor (una consulta por tipo de entidad, siempre de la
 * organización; «(no existe)» si el id ya no existe) y de los ids de su detalle. `base` aporta lo que la pantalla ya
 * conoce (el usuario que registró). Sin nombres del servidor, queda `base`.
 */
export function nombresDeAviso(
  detalle: Detalle,
  delServidor: NombresDelServidor | null | undefined,
  base: NombresDeRevision = {},
): NombresDeRevision {
  if (delServidor === null || delServidor === undefined || detalle === null) return base
  const autorizadorId = texto(detalle.autorizador_id)
  const productoId = texto(detalle.producto_id)
  const lineaId = texto(detalle.linea_id)
  const usuarios = new Map(base.usuarios)
  if (autorizadorId !== null && texto(delServidor.autorizador) !== null) usuarios.set(autorizadorId, delServidor.autorizador as string)
  const productos = new Map(base.productos)
  if (productoId !== null && texto(delServidor.producto) !== null) productos.set(productoId, delServidor.producto as string)
  const lineas = new Map(base.lineas)
  if (lineaId !== null && typeof delServidor.linea === 'number') lineas.set(lineaId, delServidor.linea)
  return { usuarios, productos, lineas, vendedorDeJornada: texto(delServidor.vendedor_de_jornada) ?? base.vendedorDeJornada }
}

type Detalle = { [clave: string]: unknown } | null

const RESOLUCIONES_DE_AUTORIZACION: Record<string, string> = {
  PERMISO_PROPIO: 'con su propio permiso',
  PIN_SUPERVISOR: 'con el PIN de un supervisor',
}

const TIPOS_DE_AUTORIZACION: Record<string, string> = { DESCUENTO: 'descuento', CREDITO: 'crédito' }

function esRegistro(valor: unknown): valor is { [clave: string]: unknown } {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor)
}

function texto(valor: unknown): string | null {
  return typeof valor === 'string' && valor !== '' ? valor : null
}

/** `"0.150000"` -> `"15 %"`; un valor que no es decimal exacto da `null`. */
function porcentajeODe(valor: unknown): string | null {
  const t = texto(valor)
  if (t === null) return null
  try {
    return formatearPorcentaje(parsearImporteDesdeApi(t))
  } catch {
    return null
  }
}

function montoODe(valor: unknown): string | null {
  const t = texto(valor)
  if (t === null) return null
  try {
    return formatearMonto(t)
  } catch {
    return null
  }
}

function lineaDeCausa(causa: unknown): string | null {
  if (!esRegistro(causa)) return null
  const conTope = (): string | null => {
    const porcentaje = porcentajeODe(causa.porcentaje_maximo)
    const tope = porcentajeODe(causa.tope)
    return porcentaje !== null && tope !== null ? `${porcentaje} con tope ${tope}` : null
  }
  switch (texto(causa.causa)) {
    case 'CALCULO':
      return 'Causa: el cálculo del teléfono no coincide con el del sistema'
    case 'TOPE': {
      const datos = conTope()
      return datos === null ? 'Causa: supera el tope' : `Causa: supera el tope (${datos})`
    }
    case 'AUTORIZADOR_SIN_PERMISO': {
      const datos = conTope()
      return datos === null
        ? 'Causa: el autorizador no tenía el permiso'
        : `Causa: el autorizador no tenía el permiso (${datos})`
    }
    case 'PERMISO':
      return 'Causa: el vendedor no tenía permiso de descuento'
    case 'DESHABILITADO':
      return 'Causa: el descuento manual estaba deshabilitado'
    case 'MOTIVO':
      return 'Causa: faltó el motivo'
    default:
      return null
  }
}

function detalleDeDescuento(detalle: Detalle): string[] {
  const causas = detalle?.causas
  if (!Array.isArray(causas)) return []
  return causas.map(lineaDeCausa).filter((linea): linea is string => linea !== null)
}

/** Lo que el servidor manda en `nombres` cuando el id ya no existe (`core/resumen.py`). */
const MARCA_NO_EXISTE = '(no existe)'

function detalleDeAutorizacion(detalle: Detalle, nombres: NombresDeRevision): string[] {
  if (detalle === null) return []
  const id = texto(detalle.autorizador_id)
  const delServidor = id === null ? undefined : nombres.usuarios?.get(id)
  // El servidor marca «(no existe)» un id que ya no existe; acá se lee como frase (revisión del usuario, 2026-11-06).
  const nombre = delServidor === MARCA_NO_EXISTE ? 'un usuario que no existe' : (delServidor ?? 'un usuario')
  const tipo = TIPOS_DE_AUTORIZACION[texto(detalle.tipo) ?? ''] ?? 'autorización'
  const clave = texto(detalle.resolucion) ?? ''
  const resolucion = RESOLUCIONES_DE_AUTORIZACION[clave] ?? clave
  const permiso = detalle.autorizador_con_permiso === true ? 'conserva' : 'ya no tiene'
  const dentro = resolucion === '' ? tipo : `${tipo}, ${resolucion}`
  return [`Autorizó ${nombre} (${dentro}); ${permiso} el permiso`]
}

function evaluacion(valor: unknown): string | null {
  if (!esRegistro(valor)) return null
  const disponible = montoODe(valor.disponible) ?? 'sin límite'
  const exceso = montoODe(valor.exceso)
  return exceso === null ? null : `disponible ${disponible}, exceso ${exceso}`
}

function detalleDeExceso(detalle: Detalle): string[] {
  if (detalle === null) return []
  const telefono = evaluacion(detalle.dispositivo)
  const sistema = evaluacion(detalle.servidor)
  if (telefono === null || sistema === null) return []
  return [`Teléfono: ${telefono} · Sistema: ${sistema}`]
}

function detalleDeConsumidorFinal(detalle: Detalle): string[] {
  const total = montoODe(detalle?.total)
  const cobrado = montoODe(detalle?.cobranza)
  return total !== null && cobrado !== null ? [`Total ${total} · cobrado ${cobrado}`] : []
}

function detalleDeMedio(detalle: Detalle): string[] {
  const nombre = texto(detalle?.nombre)
  const importe = montoODe(detalle?.importe)
  return nombre !== null && importe !== null ? [`Medio ${nombre}: ${importe}`] : []
}

function detalleDeRendicion(detalle: Detalle): string[] {
  const cuando = texto(detalle?.rendida_en)
  return cuando === null ? [] : [`Rendida el ${formatearFechaHora(cuando)}`]
}

function detalleDeStockNegativo(detalle: Detalle): string[] {
  const saldo = typeof detalle?.saldo_resultante === 'number' ? detalle.saldo_resultante : detalle?.saldo
  return typeof saldo === 'number' ? [`Saldo resultante: ${formatearCantidad(saldo, null)}`] : []
}

function detalleDeLinea(detalle: Detalle, nombres: NombresDeRevision): string[] {
  const lineaId = texto(detalle?.linea_id)
  const productoId = texto(detalle?.producto_id)
  const numero = lineaId === null ? undefined : nombres.lineas?.get(lineaId)
  const producto = productoId === null ? undefined : nombres.productos?.get(productoId)
  if (producto === undefined) return []
  return [numero === undefined ? producto : `Línea ${String(numero)}: ${producto}`]
}

function detalleDeUbicacionTomada(nombres: NombresDeRevision): string[] {
  return nombres.vendedorDeJornada === undefined ? [] : [`Tomada por la jornada de ${nombres.vendedorDeJornada}`]
}

/**
 * Las líneas de detalle legible de una observación, en el orden en que se muestran. Vacío si el código no
 * tiene detalle que mostrar o el detalle no se puede leer.
 */
export function detalleDeObservacion(codigo: string, detalle: Detalle, nombres: NombresDeRevision = {}): string[] {
  switch (codigo) {
    case 'DESCUENTO_DIFIERE':
      return detalleDeDescuento(detalle)
    case 'AUTORIZACION_OFFLINE':
      return detalleDeAutorizacion(detalle, nombres)
    case 'EXCESO_CREDITO_DETECTADO_SYNC':
      return detalleDeExceso(detalle)
    case 'CONSUMIDOR_FINAL_CON_DEUDA':
      return detalleDeConsumidorFinal(detalle)
    case 'MEDIO_INACTIVO':
    case 'REFERENCIA_FALTANTE':
      return detalleDeMedio(detalle)
    case 'JORNADA_RENDIDA':
      return detalleDeRendicion(detalle)
    case 'STOCK_NEGATIVO':
      return [...detalleDeStockNegativo(detalle), ...detalleDeLinea(detalle, nombres)]
    case 'UBICACION_TOMADA_AL_SINCRONIZAR':
      return detalleDeUbicacionTomada(nombres)
    case 'PRODUCTO_DESACTIVADO':
    case 'VENTA_SIN_COSTO':
      return detalleDeLinea(detalle, nombres)
    default:
      return []
  }
}
