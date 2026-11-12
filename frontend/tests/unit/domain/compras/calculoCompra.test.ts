/**
 * `calcularLinea` / `calcularCompra` con la regla de crédito fiscal (CMP-02, CST-06,
 * change 11b, D4 y D5). Los casos comunes con el backend viven en
 * `tests/unit/calculo/cmp02.fixtures.test.ts`; acá se fija el error exacto con el
 * número de línea y el contraste inscripto / monotributista.
 */

import { describe, expect, it } from 'vitest'

import {
  calcularCompra,
  calcularLinea,
  ErrorDeCompra,
  type EntradaDeLinea,
} from '../../../../src/domain/compras/calculoCompra'

function linea(cambios: Partial<EntradaDeLinea> = {}): EntradaDeLinea {
  return {
    unidadesPresentacion: 6,
    cantidad: '1',
    valor: '6000.00',
    incluyeIva: false,
    computaCreditoFiscal: true,
    alicuota: '0.210000',
    bonificacion: '0',
    ...cambios,
  }
}

describe('calcularLinea sin crédito fiscal (CST-06, D5)', () => {
  it('Caja x12 a 21780 de un monotributista: costo base 1815, sugerido sin IVA agregado', () => {
    const calculada = calcularLinea(
      linea({ unidadesPresentacion: 12, valor: '21780.00', computaCreditoFiscal: false }),
    )

    expect(calculada.costoBase.toFixed(6)).toBe('1815.000000')
    expect(calculada.importeNeto.toFixed(2)).toBe('21780.00')
    expect(calculada.importeConIva.toFixed(2)).toBe('21780.00')
  })

  it('la misma caja de un inscripto con IVA incluido descuenta y sugiere el IVA', () => {
    const calculada = calcularLinea(
      linea({ unidadesPresentacion: 12, valor: '21780.00', incluyeIva: true }),
    )

    expect(calculada.costoBase.toFixed(6)).toBe('1500.000000')
    expect(calculada.importeNeto.toFixed(2)).toBe('18000.00')
    expect(calculada.importeConIva.toFixed(2)).toBe('21780.00')
  })

  it('incluye IVA sin crédito fiscal lanza INCLUYE_IVA_NO_APLICA', () => {
    try {
      calcularLinea(linea({ incluyeIva: true, computaCreditoFiscal: false }))
      throw new Error('debía lanzar')
    } catch (error) {
      expect(error).toBeInstanceOf(ErrorDeCompra)
      expect((error as ErrorDeCompra).codigo).toBe('INCLUYE_IVA_NO_APLICA')
    }
  })
})

describe('calcularCompra sin crédito fiscal (CST-06, D4, D5)', () => {
  it('compra del criterio 2 de un monotributista: total y sugerido iguales a la suma pagada', () => {
    const totales = calcularCompra([
      linea({ unidadesPresentacion: 6, cantidad: '10', valor: '7260.00', computaCreditoFiscal: false }),
      linea({ unidadesPresentacion: 1, cantidad: '60', valor: '1331.00', computaCreditoFiscal: false }),
    ])

    expect(totales.totalNeto.toFixed(2)).toBe('152460.00')
    expect(totales.totalFacturaSugerido.toFixed(2)).toBe('152460.00')
    expect(totales.lineas.map((l) => l.costoBase.toFixed(6))).toEqual(['1210.000000', '1331.000000'])
  })

  it.each([0, 1, 3])('el rechazo de INCLUYE_IVA_NO_APLICA indica la línea %i', (posicion) => {
    const lineas = [0, 1, 2, 3].map(() => linea({ computaCreditoFiscal: false }))
    lineas[posicion] = linea({ incluyeIva: true, computaCreditoFiscal: false })

    try {
      calcularCompra(lineas)
      throw new Error('debía lanzar')
    } catch (error) {
      expect((error as ErrorDeCompra).codigo).toBe('INCLUYE_IVA_NO_APLICA')
      expect((error as ErrorDeCompra).linea).toBe(posicion)
    }
  })
})
