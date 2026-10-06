import { formatearMonto } from '../cuentas-corrientes/presentacion'
import { parsearImporteDesdeApi } from '../../lib/money'

/**
 * Aviso del alta de compra cuando el proveedor tiene saldo a nuestro favor (change 12, tarea
 * 9.4; PAG-02, `design.md` D3). Es informativo: no cambia la condición ni impide confirmar.
 * `null` con saldo cero, con deuda o mientras el saldo no se pudo leer. El saldo se formatea
 * desde el string de la API, sin pasar por `number` (INV-03).
 */
export function avisoDeSaldoAFavorEnCompra(saldo: string | undefined): string | null {
  if (saldo === undefined) return null
  const valor = parsearImporteDesdeApi(saldo)
  if (!valor.isNegative()) return null
  return `Este proveedor tiene saldo a nuestro favor de ${formatearMonto(valor.neg().toFixed(2))}: cargada a crédito, la compra se descuenta de ese saldo`
}
