import { describe, expect, it } from 'vitest'

import { avisoDeSaldoAFavorEnCompra } from '../../../../src/domain/compras/saldoAFavor'
import { rutaDeOperacionDeMovimiento } from '../../../../src/domain/cuentas-corrientes/enlaces'
import type { CodigoPermiso } from '../../../../src/domain/identidad/permisos'
import {
  etiquetaDeOrigen,
  puedeAnularse,
  textoDeSaldoTrasAnular,
} from '../../../../src/domain/pagos-proveedores/presentacion'

const ID = '11111111-1111-4111-8111-111111111111'

function tienen(...permisos: CodigoPermiso[]) {
  return (permiso: CodigoPermiso) => permisos.includes(permiso)
}

describe('puedeAnularse (CMP-05, D2)', () => {
  it('un pago independiente confirmado se anula', () => {
    expect(puedeAnularse({ estado: 'CONFIRMADA', origen: 'INDEPENDIENTE', compra_estado: null })).toBe(true)
  })

  it('un pago ya anulado no se anula', () => {
    expect(puedeAnularse({ estado: 'ANULADA', origen: 'INDEPENDIENTE', compra_estado: null })).toBe(false)
  })

  it('el pago de una compra vigente no se anula por separado', () => {
    expect(puedeAnularse({ estado: 'CONFIRMADA', origen: 'COMPRA', compra_estado: 'CONFIRMADA' })).toBe(false)
  })

  it('el pago de una compra ya anulada sin devolución sí se anula', () => {
    expect(puedeAnularse({ estado: 'CONFIRMADA', origen: 'COMPRA', compra_estado: 'ANULADA' })).toBe(true)
  })
})

describe('textoDeSaldoTrasAnular (PAG-03)', () => {
  it('anular un pago de 52.460,00 con deuda de 100.000,00 vuelve a 152.460,00', () => {
    expect(textoDeSaldoTrasAnular('100000.00', '52460.00')).toBe('Le debemos $ 152.460,00')
  })

  it('anular el pago de una compra anulada sin devolución con saldo a favor lo deja en cero', () => {
    expect(textoDeSaldoTrasAnular('-152460.00', '152460.00')).toBe('Saldo $ 0,00')
  })
})

describe('etiquetaDeOrigen', () => {
  it('traduce los orígenes conocidos y deja pasar uno desconocido', () => {
    expect(etiquetaDeOrigen('COMPRA')).toBe('Compra de contado')
    expect(etiquetaDeOrigen('INDEPENDIENTE')).toBe('Pago independiente')
    expect(etiquetaDeOrigen('OTRO')).toBe('OTRO')
  })
})

describe('avisoDeSaldoAFavorEnCompra (PAG-02, D3)', () => {
  it('con saldo -152460.00 avisa el saldo a favor y que la compra a crédito se descuenta', () => {
    expect(avisoDeSaldoAFavorEnCompra('-152460.00')).toBe(
      'Este proveedor tiene saldo a nuestro favor de $ 152.460,00: cargada a crédito, la compra se descuenta de ese saldo',
    )
  })

  it('con deuda, con saldo cero o sin saldo leído no avisa', () => {
    expect(avisoDeSaldoAFavorEnCompra('153720.00')).toBeNull()
    expect(avisoDeSaldoAFavorEnCompra('0.00')).toBeNull()
    expect(avisoDeSaldoAFavorEnCompra(undefined)).toBeNull()
  })
})

describe('rutaDeOperacionDeMovimiento (CC-01, D7)', () => {
  it('PAGO y ANULACION_PAGO enlazan al pago con cualquiera de los dos permisos de pago', () => {
    expect(rutaDeOperacionDeMovimiento('PAGO', ID, tienen('REGISTRAR_PAGO_PROVEEDOR'))).toBe(`/admin/pagos-proveedores/${ID}`)
    expect(rutaDeOperacionDeMovimiento('ANULACION_PAGO', ID, tienen('ANULAR_PAGO_PROVEEDOR'))).toBe(`/admin/pagos-proveedores/${ID}`)
  })

  it('COMPRA y ANULACION_COMPRA enlazan a la compra con cualquiera de los dos permisos de compra', () => {
    expect(rutaDeOperacionDeMovimiento('COMPRA', ID, tienen('REGISTRAR_COMPRA'))).toBe(`/admin/compras/${ID}`)
    expect(rutaDeOperacionDeMovimiento('ANULACION_COMPRA', ID, tienen('ANULAR_COMPRA'))).toBe(`/admin/compras/${ID}`)
  })

  it('sin el permiso de lectura de la operación no hay enlace', () => {
    expect(rutaDeOperacionDeMovimiento('PAGO', ID, tienen('GESTIONAR_PROVEEDORES', 'REGISTRAR_COMPRA'))).toBeNull()
    expect(rutaDeOperacionDeMovimiento('COMPRA', ID, tienen('GESTIONAR_PROVEEDORES', 'REGISTRAR_PAGO_PROVEEDOR'))).toBeNull()
  })

  it('los demás tipos no enlazan a nada', () => {
    expect(rutaDeOperacionDeMovimiento('SALDO_INICIAL', ID, tienen('REGISTRAR_COMPRA', 'REGISTRAR_PAGO_PROVEEDOR'))).toBeNull()
    expect(rutaDeOperacionDeMovimiento('VENTA', ID, tienen('REGISTRAR_COMPRA', 'REGISTRAR_PAGO_PROVEEDOR'))).toBeNull()
  })
})
