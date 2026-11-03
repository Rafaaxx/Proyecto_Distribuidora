import { formatearFechaHora } from '../../../lib/fecha'
import type { ErrorDeSincronizacion } from '../../../sync/sincronizar'

/**
 * Textos del estado de la sincronización de `/ruta` (change 22b, `design.md` D8; SYN-04, SYN-06,
 * SYN-09, `02` §12.3, §13.3). Funciones puras: las pantallas solo las muestran.
 */
export const TEXTO_DE_OTRA_PESTANA = 'Sincronizando en otra pestaña'
export const TEXTO_ENVIANDO = 'Enviando…'
export const TEXTO_DE_SESION_VENCIDA = 'Iniciá sesión con señal para enviar las ventas'
export const TEXTO_DE_NO_SE_PUDO_ENVIAR = 'No se pudo enviar'
/** Texto de la tarea 10.1 para «Sincronizar» sin señal (no figura en los aprobados de 0.2). */
export const TEXTO_DE_SIN_SENAL = 'Sincronizar requiere conexión.'

/**
 * Inicio y pantalla «Sincronización» (change 22d, D10, aprobado en 0.2): «Todo enviado», «1 venta
 * sin enviar», «N ventas sin enviar», «1 anulación sin enviar» y «N ventas y M anulaciones sin
 * enviar».
 */
export function textoDePendientes(ventas: number, anulaciones: number): string {
  if (ventas === 0 && anulaciones === 0) return 'Todo enviado'
  const deVentas = ventas === 1 ? '1 venta' : `${ventas} ventas`
  const deAnulaciones = anulaciones === 1 ? '1 anulación' : `${anulaciones} anulaciones`
  if (anulaciones === 0) return `${deVentas} sin enviar`
  if (ventas === 0) return `${deAnulaciones} sin enviar`
  return `${deVentas} y ${deAnulaciones} sin enviar`
}

/** Solo ventas (22a). */
export function textoDeSinEnviar(cantidad: number): string {
  return textoDePendientes(cantidad, 0)
}

/** Cabecera: más corto para el teléfono. */
export function textoDeCabecera(cantidad: number): string {
  return cantidad === 0 ? 'Todo enviado' : `${cantidad} sin enviar`
}

export function textoDeRechazadas(cantidad: number): string {
  return cantidad === 1 ? '1 rechazada' : `${cantidad} rechazadas`
}

export function textoDeUltimaSincronizacion(momentoIso: string | null): string {
  return `Última sincronización: ${momentoIso === null ? '—' : formatearFechaHora(momentoIso).trim()}`
}

export interface TextoDeError {
  texto: string
  codigo: string | null
}

/** Último error del envío: sesión vencida pide iniciar sesión con señal; el resto, «No se pudo enviar» con su código. */
export function textoDelUltimoError(error: ErrorDeSincronizacion): TextoDeError {
  if (error.tipo === 'sesion_vencida') return { texto: TEXTO_DE_SESION_VENCIDA, codigo: null }
  return { texto: TEXTO_DE_NO_SE_PUDO_ENVIAR, codigo: error.codigo }
}

/** Lee el JSON de `meta.ultimo_error_sync`; un valor ilegible se ignora. */
export function leerUltimoError(valor: string | undefined): ErrorDeSincronizacion | null {
  if (valor === undefined) return null
  try {
    const dato = JSON.parse(valor) as Partial<ErrorDeSincronizacion>
    if (dato.tipo !== 'transitorio' && dato.tipo !== 'sesion_vencida' && dato.tipo !== 'error_pedido') return null
    return { tipo: dato.tipo, codigo: dato.codigo ?? null, en: dato.en ?? '' }
  } catch {
    return null
  }
}
