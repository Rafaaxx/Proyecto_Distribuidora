import { avisoDeSaldoAFavorTrasPago } from './formularioPago'

/**
 * Qué confirmación corresponde antes de enviar un pago según lo que se sabe del saldo del
 * proveedor (PAG-02, `design.md` D3: pagar de más sigue permitido, pero nunca sin aviso).
 * Si el saldo no se pudo leer no se puede saber si el pago lo supera: se pide confirmar igual.
 */

export const AVISO_SALDO_ILEGIBLE =
  'No pudimos leer el saldo del proveedor; no podemos avisarte si este pago supera la deuda.'

export type LecturaDeSaldo =
  | { estado: 'cargando' }
  | { estado: 'error' }
  | { estado: 'leido'; saldo: string }

export type ConfirmacionDePago =
  | { tipo: 'ninguna' }
  | { tipo: 'saldo-a-favor'; mensaje: string }
  | { tipo: 'saldo-ilegible'; mensaje: string }
  | { tipo: 'esperar' }

export function decidirConfirmacionDePago(lectura: LecturaDeSaldo, importe: string): ConfirmacionDePago {
  switch (lectura.estado) {
    case 'cargando':
      return { tipo: 'esperar' }
    case 'error':
      return { tipo: 'saldo-ilegible', mensaje: AVISO_SALDO_ILEGIBLE }
    case 'leido': {
      const mensaje = avisoDeSaldoAFavorTrasPago(lectura.saldo, importe)
      return mensaje === null ? { tipo: 'ninguna' } : { tipo: 'saldo-a-favor', mensaje }
    }
  }
}
