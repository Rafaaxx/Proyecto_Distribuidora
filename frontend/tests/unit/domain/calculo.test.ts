/**
 * Change 18a, tarea 2.2: comportamientos del motor de la venta más allá de los casos compartidos
 * (espejo de `backend/tests/unit/test_ventas_domain_calculo.py`; VTA-02, VTA-04, INV-03, INV-14).
 */

import { describe, expect, it } from 'vitest'

import { calcularVenta, ErrorDeCalculoDeVenta } from '../../../src/domain/calculo'
import type { LineaCalculo } from '../../../src/domain/calculo'

function linea(id: string, cambios: Partial<LineaCalculo> = {}): LineaCalculo {
  return {
    id,
    precioReferencia: '12500.00',
    unidadesReferencia: 6,
    cantidadBase: 15,
    alicuota: '0.210000',
    productoId: `prod-${id}`,
    categoriaId: 'cat',
    marcaId: 'marca',
    descuentoManual: null,
    ...cambios,
  }
}

describe('calcularVenta', () => {
  it.each(['B', 'C', 'Z', 'a', ''])('rechaza el modo %j', (modo) => {
    expect(() => calcularVenta(modo, [linea('l-1')], [], null)).toThrow(ErrorDeCalculoDeVenta)
    try {
      calcularVenta(modo, [linea('l-1')], [], null)
    } catch (error) {
      expect((error as ErrorDeCalculoDeVenta).codigo).toBe('MODO_IMPOSITIVO_NO_SOPORTADO')
    }
  })

  it("una venta sin líneas se rechaza con VENTA_SIN_LINEAS", () => {
    const lineas: LineaCalculo[] = []
    expect(() => calcularVenta('A', lineas, [], null)).toThrowError(
      expect.objectContaining({ codigo: 'VENTA_SIN_LINEAS' }),
    )
  })

  it('un descuento manual del 100 % deja neto, IVA y total en cero', () => {
    const r = calcularVenta('A', [linea('l-1', { descuentoManual: '1.000000' })], [], null)
    expect([r.lineas[0]?.neto.toFixed(2), r.totalIva.toFixed(2), r.total.toFixed(2)]).toEqual([
      '0.00',
      '0.00',
      '0.00',
    ])
    expect(r.lineas[0]?.bruto.toFixed(2)).toBe('31250.00')
  })

  it('el manual propio reemplaza al general y el total cierra con la suma de netos', () => {
    const r = calcularVenta(
      'A',
      [
        linea('l-1', { cantidadBase: 12, descuentoManual: '0.500000' }),
        linea('l-2', { cantidadBase: 3 }),
      ],
      [],
      '0.100000',
    )
    expect(r.lineas.map((l) => l.neto.toFixed(2))).toEqual(['12500.00', '5625.00'])
    expect(r.total.toFixed(2)).toBe('18125.00')
  })

  it('conserva la alícuota de cada línea con IVA cero y el orden de entrada', () => {
    const r = calcularVenta(
      'A',
      [linea('z', { alicuota: '0.105000' }), linea('a', { alicuota: '0.210000' })],
      [],
      null,
    )
    expect(r.lineas.map((l) => [l.id, l.alicuota.toFixed(6), l.importeIva.toFixed(2)])).toEqual([
      ['z', '0.105000', '0.00'],
      ['a', '0.210000', '0.00'],
    ])
  })

  it.each([0.21, 21, null])('rechaza una alícuota que no es cadena decimal (%j)', (alicuota) => {
    expect(() =>
      calcularVenta('A', [linea('l-1', { alicuota: alicuota as unknown as string })], [], null),
    ).toThrowError(expect.objectContaining({ codigo: 'ENTRADA_NO_ES_DINERO_EXACTO' }))
  })
})
