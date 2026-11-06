import { describe, expect, it } from 'vitest'

import {
  OPCIONES_DE_TIPO,
  etiquetaDeTipoDeOperacion,
  puedeVerOperacion,
  rutaDeOperacion,
  tituloDeOperacion,
} from '../../../../src/domain/revision/operaciones'

/** Change 25, tarea 13.2 (D3, D4, D11): cómo se nombra y a dónde lleva cada operación de la bandeja. */
describe('operaciones de la bandeja (D3, D4, D11)', () => {
  it('ofrece los cinco tipos de operación con su etiqueta', () => {
    expect(OPCIONES_DE_TIPO.map((o) => o.valor)).toEqual(['VENTA', 'COBRANZA', 'COMPRA', 'TRANSFERENCIA', 'AJUSTE_STOCK'])
    expect(etiquetaDeTipoDeOperacion('AJUSTE_STOCK')).toBe('Ajuste de stock')
    expect(etiquetaDeTipoDeOperacion('OTRA')).toBe('OTRA')
  })

  it('sin resumen se muestra «Operación {tipo}»', () => {
    expect(tituloDeOperacion('VENTA', { titulo: 'Venta 0001-00000012' })).toBe('Venta 0001-00000012')
    expect(tituloDeOperacion('COBRANZA', null)).toBe('Operación Cobranza')
    expect(tituloDeOperacion('RARA', null)).toBe('Operación RARA')
  })

  it('«Ver» lleva a la pantalla de cada tipo', () => {
    expect(rutaDeOperacion('VENTA', 'v1')).toBe('/admin/ventas/v1')
    expect(rutaDeOperacion('COBRANZA', 'c1')).toBe('/admin/cobranzas/c1')
    expect(rutaDeOperacion('COMPRA', 'k1')).toBe('/admin/compras/k1')
    expect(rutaDeOperacion('TRANSFERENCIA', 't1')).toBe('/admin/stock/transferencias/t1')
    expect(rutaDeOperacion('AJUSTE_STOCK', 'a1')).toBe('/admin/stock/ajustes/a1')
    expect(rutaDeOperacion('RARA', 'x')).toBeNull()
  })

  it('«Ver» se ofrece solo si el usuario puede abrir la operación (SEG-06)', () => {
    const con = (...permisos: string[]) => (permiso: string) => permisos.includes(permiso)
    expect(puedeVerOperacion('VENTA', con('VENDER'))).toBe(true)
    expect(puedeVerOperacion('VENTA', con('ANULAR_VENTA'))).toBe(true)
    expect(puedeVerOperacion('VENTA', con('REGISTRAR_COBRANZA'))).toBe(false)
    expect(puedeVerOperacion('COBRANZA', con('ANULAR_COBRANZA'))).toBe(true)
    expect(puedeVerOperacion('COMPRA', con())).toBe(false)
    expect(puedeVerOperacion('TRANSFERENCIA', con('TRANSFERIR_STOCK'))).toBe(true)
    expect(puedeVerOperacion('AJUSTE_STOCK', con('AJUSTAR_STOCK'))).toBe(true)
    expect(puedeVerOperacion('RARA', con('VENDER'))).toBe(false)
  })
})
