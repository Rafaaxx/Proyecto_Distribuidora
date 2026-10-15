/**
 * Evaluación del descuento manual: habilitación, permiso, motivo, tope y autorización (DSC-06,
 * TR-02, INV-03; `design.md` D11, D12, D14 del change 16). Espejo de
 * `backend/app/modules/descuentos/domain/manual.py`: mismos casos de
 * `shared/fixtures/calculo/dsc-06-descuento-manual.json` (`"motor": "dsc06"`, ADR-016).
 *
 * Función pura: solo lee y decide; no verifica ningún PIN ni registra nada (change 18b). Se evalúa
 * UNA vez por venta con el mayor porcentaje manual que quedó aplicado en alguna línea
 * (`ResultadoDescuentos.porcentajeManualMaximo`, D11): una sola resolución cubre todas las líneas.
 *
 * Orden (D12): organización deshabilitada; sin `DESCUENTO_MANUAL`; motivo obligatorio y ausente;
 * porcentaje <= tope aplicable (`DENTRO_DEL_TOPE`); si lo supera, `PERMISO_PROPIO` con
 * `AUTORIZAR_DESCUENTO` o `AUTORIZADO_POR_SUPERVISOR` con un autorizador que lo tenga. Quien
 * autoriza no queda limitado por su propio tope. Nada se convierte a `number` (INV-03).
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi } from '../../lib/money'
import { ErrorDeDescuentos } from './errores'
import { validarPorcentajeManual } from './motor'

export const PERMISO_DESCUENTO_MANUAL = 'DESCUENTO_MANUAL'
export const PERMISO_AUTORIZAR_DESCUENTO = 'AUTORIZAR_DESCUENTO'

export type ResolucionManual = 'DENTRO_DEL_TOPE' | 'PERMISO_PROPIO' | 'AUTORIZADO_POR_SUPERVISOR'

/** Otro usuario de la organización que autoriza, con los permisos que tiene hoy. */
export interface Autorizador {
  usuarioId: string
  permisos: readonly string[]
}

export interface EntradaManual {
  usuarioId: string
  descuentoManualHabilitado: boolean
  /** Nulo = parámetro sin definir: el motivo no es obligatorio (D14). */
  motivoObligatorio: boolean | null
  permisosUsuario: readonly string[]
  topeRol: string
  /** Tope propio del usuario; si existe, manda sobre el del rol. */
  topePropio: string | null
  /** El mayor porcentaje manual que quedó aplicado en alguna línea de la venta. */
  porcentajeMaximo: string
  motivo: string | null
  autorizador: Autorizador | null
}

/** Lo que la venta registra (DSC-08, SEG-05). `autorizadorId` es nulo dentro del tope. */
export interface ResultadoManual {
  topeAplicado: Importe
  requirioAutorizacion: boolean
  resolucion: ResolucionManual
  autorizadorId: string | null
}

export function evaluarDescuentoManual(entrada: EntradaManual): ResultadoManual {
  validarPorcentajeManual(entrada.porcentajeMaximo, 'El mayor porcentaje manual de la venta')

  if (!entrada.descuentoManualHabilitado) {
    throw new ErrorDeDescuentos(
      'DESCUENTO_MANUAL_DESHABILITADO',
      'La organización no tiene habilitado el descuento manual.',
    )
  }
  if (!entrada.permisosUsuario.includes(PERMISO_DESCUENTO_MANUAL)) {
    throw new ErrorDeDescuentos('PERMISO_REQUERIDO', `Falta el permiso ${PERMISO_DESCUENTO_MANUAL}.`)
  }
  if (entrada.motivoObligatorio === true && (entrada.motivo ?? '').trim() === '') {
    throw new ErrorDeDescuentos(
      'MOTIVO_REQUERIDO',
      'La organización exige un motivo para el descuento manual.',
    )
  }

  const tope = parsearImporteDesdeApi(entrada.topePropio ?? entrada.topeRol)
  if (parsearImporteDesdeApi(entrada.porcentajeMaximo).lessThanOrEqualTo(tope)) {
    return {
      topeAplicado: tope,
      requirioAutorizacion: false,
      resolucion: 'DENTRO_DEL_TOPE',
      autorizadorId: null,
    }
  }

  if (entrada.permisosUsuario.includes(PERMISO_AUTORIZAR_DESCUENTO)) {
    return {
      topeAplicado: tope,
      requirioAutorizacion: true,
      resolucion: 'PERMISO_PROPIO',
      autorizadorId: entrada.usuarioId,
    }
  }
  if (entrada.autorizador === null) {
    throw new ErrorDeDescuentos(
      'AUTORIZACION_REQUERIDA',
      'El descuento manual supera el tope y hace falta una autorización.',
    )
  }
  if (!entrada.autorizador.permisos.includes(PERMISO_AUTORIZAR_DESCUENTO)) {
    throw new ErrorDeDescuentos(
      'AUTORIZADOR_SIN_PERMISO',
      'El autorizador no tiene el permiso AUTORIZAR_DESCUENTO.',
    )
  }
  return {
    topeAplicado: tope,
    requirioAutorizacion: true,
    resolucion: 'AUTORIZADO_POR_SUPERVISOR',
    autorizadorId: entrada.autorizador.usuarioId,
  }
}
