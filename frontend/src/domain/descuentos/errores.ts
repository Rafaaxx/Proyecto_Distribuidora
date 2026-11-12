/**
 * Errores de dominio del motor de descuentos, con el mismo código estable que el backend
 * (`backend/app/modules/descuentos/domain/errores.py`; `CLAUDE.md` §5).
 */

export type CodigoErrorDescuentos =
  | 'DESCUENTO_MANUAL_INVALIDO'
  | 'LINEA_DESCUENTO_INVALIDA'
  | 'REGLA_DESCUENTO_INVALIDA'
  | 'ENTRADA_NO_ES_DINERO_EXACTO'
  | 'DESCUENTO_MANUAL_DESHABILITADO'
  | 'PERMISO_REQUERIDO'
  | 'MOTIVO_REQUERIDO'
  | 'AUTORIZACION_REQUERIDA'
  | 'AUTORIZADOR_SIN_PERMISO'

export class ErrorDeDescuentos extends Error {
  readonly codigo: CodigoErrorDescuentos

  constructor(codigo: CodigoErrorDescuentos, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeDescuentos'
    this.codigo = codigo
  }
}
