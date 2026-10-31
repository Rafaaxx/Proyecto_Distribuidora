import type { VersionLocal } from '../../lib/dispositivo/db'
import {
  FALTA_CONTADO_DE_CONSUMIDOR_FINAL,
  evaluarContadoDeConsumidorFinal,
} from '../ventas/calculoDeVenta'
import {
  necesidadDeAutorizacionDeDescuento,
  type ContextoDeDescuento,
  type NecesidadDeDescuento,
} from '../ventas/descuentosDeVenta'
import { MENSAJE_SIN_PRECIO } from '../ventas/pedido'
import { armarCreditoDeRuta, type CreditoDeRuta } from './creditoDeRuta'

/**
 * Reglas que el teléfono aplica antes de encolar (change 22a, `design.md` D7, D8; CLI-02, CLI-03,
 * VTA-11, PRC-21, VTA-10, DSC-06, ADR-054). Funciones puras sobre los datos y los permisos del
 * bootstrap: devuelven el texto del bloqueo o `null`. Reutilizan el cálculo y los textos de
 * `/admin`; ningún importe pasa por `number` (INV-03).
 */
export const PERMISO_VENDER_CLIENTE_SUSPENDIDO = 'VENDER_CLIENTE_SUSPENDIDO'
export const PERMISO_USAR_LISTA_ANTERIOR = 'USAR_LISTA_ANTERIOR'

/** CLI-02: un cliente suspendido no se vende sin el permiso (sin PIN de supervisor). */
export function bloqueoPorCliente(
  cliente: { estado: string },
  permisos: readonly string[],
): string | null {
  if (cliente.estado !== 'SUSPENDIDO') return null
  if (permisos.includes(PERMISO_VENDER_CLIENTE_SUSPENDIDO)) return null
  return 'El cliente está suspendido: no se le puede vender.'
}

/** CLI-03, VTA-11: al consumidor final, cobranza exactamente igual al total (ni menos ni más). */
export function bloqueoPorConsumidorFinal(
  cliente: { es_consumidor_final: boolean },
  total: string,
  cobrado: string,
): string | null {
  return evaluarContadoDeConsumidorFinal(cliente.es_consumidor_final, total, cobrado).cumple
    ? null
    : FALTA_CONTADO_DE_CONSUMIDOR_FINAL
}

/** D8: el crédito del consumidor final se evalúa con límite cero y queda `SIN_EXCESO` (CLI-03). */
export function creditoDeConsumidorFinal(saldoConsiderado: string, total: string, cobranza: string): CreditoDeRuta {
  return armarCreditoDeRuta({
    limite: '0.00',
    saldoConsiderado,
    politica: 'BLOQUEAR',
    toleranciaTipo: null,
    toleranciaValor: null,
    total,
    cobranza,
    aceptaExceso: false,
    usuarioId: '',
    permisosUsuario: [],
    autorizador: null,
  })
}

/** PRC-21: elegir otra lista o una versión anterior exige `USAR_LISTA_ANTERIOR`. */
export function puedeElegirOtraLista(permisos: readonly string[]): boolean {
  return permisos.includes(PERMISO_USAR_LISTA_ANTERIOR)
}

/**
 * PRC-21: versión anterior = publicada con vigencia desde no posterior al momento. La programada
 * (desde futuro), el borrador y la anulada no son elegibles. De mayor a menor número.
 */
export function versionesElegiblesComoAnterior(versiones: readonly VersionLocal[], momento: Date): VersionLocal[] {
  const t = momento.getTime()
  return versiones
    .filter(
      (v) =>
        v.estado !== 'BORRADOR' &&
        v.estado !== 'ANULADA' &&
        v.estado !== 'PROGRAMADA' &&
        new Date(v.vigencia_desde).getTime() <= t,
    )
    .sort((a, b) => b.numero - a.numero)
}

/** PRC-21: con otra versión elegida y motivo exigido por la organización, falta el motivo. */
export function bloqueoPorLista(entrada: {
  usaOtraVersion: boolean
  motivoObligatorio: boolean
  motivoId: string
}): string | null {
  if (!entrada.usaOtraVersion || !entrada.motivoObligatorio) return null
  return entrada.motivoId.trim() === '' ? 'Elegí el motivo para usar otra lista o una versión anterior.' : null
}

/** VTA-10: un producto sin precio en la versión no se puede agregar. */
export function puedeAgregarProducto(
  precio: string | null,
): { agregable: true; mensaje: null } | { agregable: false; mensaje: string } {
  return precio === null ? { agregable: false, mensaje: MENSAJE_SIN_PRECIO } : { agregable: true, mensaje: null }
}

/** DSC-06 con el contexto del bootstrap: si el mayor manual cabe en el tope o pide autorizador. */
export function estadoDelDescuentoManual(
  mayorManual: string | null,
  contexto: ContextoDeDescuento,
): NecesidadDeDescuento {
  return necesidadDeAutorizacionDeDescuento(mayorManual, contexto)
}
