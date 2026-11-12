import { describe, expect, it } from 'vitest'

import { rutaDeOperacionDeMovimiento } from '../../../../src/domain/cuentas-corrientes/enlaces'

describe('enlace de un movimiento de cobranza a su cobranza (D14, D19)', () => {
  const con = (...permisos: string[]) => (permiso: string) => permisos.includes(permiso)

  it.each(['COBRANZA', 'ANULACION_COBRANZA'])('%s enlaza con REGISTRAR_COBRANZA o con ANULAR_COBRANZA', (tipo) => {
    expect(rutaDeOperacionDeMovimiento(tipo, 'x1', con('REGISTRAR_COBRANZA') as never)).toBe('/admin/cobranzas/x1')
    expect(rutaDeOperacionDeMovimiento(tipo, 'x1', con('ANULAR_COBRANZA') as never)).toBe('/admin/cobranzas/x1')
  })

  it('sin permisos de cobranza no hay enlace, y los de pagos no lo habilitan', () => {
    expect(rutaDeOperacionDeMovimiento('COBRANZA', 'x1', con('GESTIONAR_CLIENTES', 'REGISTRAR_PAGO_PROVEEDOR') as never)).toBeNull()
  })

  it('en la cuenta de un cliente solo las cobranzas enlazan; en la de un proveedor, pagos y compras', () => {
    const todo = con('REGISTRAR_COBRANZA', 'REGISTRAR_PAGO_PROVEEDOR', 'REGISTRAR_COMPRA') as never

    expect(rutaDeOperacionDeMovimiento('COMPRA', 'c', todo, 'CLIENTE')).toBeNull()
    expect(rutaDeOperacionDeMovimiento('COBRANZA', 'c', todo, 'CLIENTE')).toBe('/admin/cobranzas/c')
    expect(rutaDeOperacionDeMovimiento('COBRANZA', 'c', todo, 'PROVEEDOR')).toBeNull()
    expect(rutaDeOperacionDeMovimiento('PAGO', 'p', todo, 'PROVEEDOR')).toBe('/admin/pagos-proveedores/p')
  })
})
