import type { CodigoPermiso } from '../identidad/permisos'

/**
 * Enlace de un movimiento del estado de cuenta de un proveedor a la operación que lo
 * originó (change 12, tarea 9.3; CC-01 operación origen, `design.md` D7). Solo se ofrece a
 * quien tiene permiso de lectura de esa operación: pagos con `REGISTRAR_PAGO_PROVEEDOR` o
 * `ANULAR_PAGO_PROVEEDOR`, compras con `REGISTRAR_COMPRA` o `ANULAR_COMPRA`. Devuelve
 * `null` cuando no hay enlace (sin permiso o un tipo sin pantalla de detalle). Cobranzas
 * (change 17): `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`.
 */
type TienePermiso = (permiso: CodigoPermiso) => boolean

const LECTURA_DE_PAGOS: readonly CodigoPermiso[] = ['REGISTRAR_PAGO_PROVEEDOR', 'ANULAR_PAGO_PROVEEDOR']
const LECTURA_DE_COMPRAS: readonly CodigoPermiso[] = ['REGISTRAR_COMPRA', 'ANULAR_COMPRA']
const LECTURA_DE_COBRANZAS: readonly CodigoPermiso[] = ['REGISTRAR_COBRANZA', 'ANULAR_COBRANZA']

/**
 * Con `cuentaTipo` (change 17, D19) solo enlazan los tipos de esa cuenta: pagos y compras en la de
 * un proveedor, cobranzas en la de un cliente. Sin él, el comportamiento es el de antes.
 */
export function rutaDeOperacionDeMovimiento(
  tipo: string,
  origenId: string,
  tiene: TienePermiso,
  cuentaTipo?: 'CLIENTE' | 'PROVEEDOR',
): string | null {
  const deProveedor = cuentaTipo === undefined || cuentaTipo === 'PROVEEDOR'
  const deCliente = cuentaTipo === undefined || cuentaTipo === 'CLIENTE'
  if (deProveedor && (tipo === 'PAGO' || tipo === 'ANULACION_PAGO')) {
    return LECTURA_DE_PAGOS.some(tiene) ? `/admin/pagos-proveedores/${origenId}` : null
  }
  if (deProveedor && (tipo === 'COMPRA' || tipo === 'ANULACION_COMPRA')) {
    return LECTURA_DE_COMPRAS.some(tiene) ? `/admin/compras/${origenId}` : null
  }
  if (deCliente && (tipo === 'COBRANZA' || tipo === 'ANULACION_COBRANZA')) {
    return LECTURA_DE_COBRANZAS.some(tiene) ? `/admin/cobranzas/${origenId}` : null
  }
  return null
}
