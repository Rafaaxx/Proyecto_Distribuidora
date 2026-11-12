import { describe, expect, it } from 'vitest'

import { rutaDeOperacionDeMovimiento } from '../../../../src/domain/cuentas-corrientes/enlaces'

/** CC-07, CC-05, `01` §19: el movimiento VENTA lleva al detalle de la venta con VENDER o ANULAR_VENTA. */
describe('enlace de un movimiento VENTA a su venta (change 18a, tarea 12.4)', () => {
  const con = (...permisos: string[]) => (permiso: string) => permisos.includes(permiso)

  it('VENTA enlaza con VENDER o con ANULAR_VENTA', () => {
    expect(rutaDeOperacionDeMovimiento('VENTA', 'v1', con('VENDER') as never)).toBe('/admin/ventas/v1')
    expect(rutaDeOperacionDeMovimiento('VENTA', 'v1', con('ANULAR_VENTA') as never)).toBe('/admin/ventas/v1')
  })

  it('sin esos permisos no hay enlace, aunque tenga permisos de clientes o de cobranzas', () => {
    expect(rutaDeOperacionDeMovimiento('VENTA', 'v1', con('GESTIONAR_CLIENTES', 'REGISTRAR_COBRANZA') as never)).toBeNull()
  })

  it('solo en la cuenta de un cliente: en la de un proveedor un VENTA no enlaza', () => {
    const todo = con('VENDER') as never
    expect(rutaDeOperacionDeMovimiento('VENTA', 'v1', todo, 'CLIENTE')).toBe('/admin/ventas/v1')
    expect(rutaDeOperacionDeMovimiento('VENTA', 'v1', todo, 'PROVEEDOR')).toBeNull()
  })

  it('la anulación de venta todavía no tiene pantalla: no enlaza', () => {
    expect(rutaDeOperacionDeMovimiento('ANULACION_VENTA', 'v1', con('VENDER', 'ANULAR_VENTA') as never)).toBeNull()
  })
})
