/**
 * Errores de dominio del motor de crédito, con el mismo código estable que el backend
 * (`backend/app/modules/clientes/domain/errores.py`; `CLAUDE.md` §5).
 */

export type CodigoErrorCredito =
  | 'ENTRADA_NO_ES_DINERO_EXACTO'
  | 'LIMITE_CREDITO_INVALIDO'
  | 'POLITICA_CREDITO_INVALIDA'
  | 'TOLERANCIA_OFFLINE_INVALIDA'
  | 'MODO_CREDITO_INVALIDO'
  | 'EXCESO_CREDITO_SIN_ACEPTAR'
  | 'CREDITO_EXCEDIDO'
  | 'AUTORIZACION_CREDITO_REQUERIDA'
  | 'AUTORIZADOR_SIN_PERMISO'

export class ErrorDeCredito extends Error {
  readonly codigo: CodigoErrorCredito

  constructor(codigo: CodigoErrorCredito, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeCredito'
    this.codigo = codigo
  }
}
