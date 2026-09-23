import { describe, expect, it } from 'vitest'

import { esquemaProducto } from '../../../../src/domain/catalogo/productoSchema'

const CATEGORIA_ID = '11111111-1111-4111-8111-111111111111'
const ALICUOTA_ID = '22222222-2222-4222-8222-222222222222'

function productoValido(overrides: Partial<Parameters<typeof esquemaProducto.parse>[0]> = {}) {
  return {
    codigo: 'GAS-001',
    nombre: 'Gaseosa cola',
    categoriaId: CATEGORIA_ID,
    marcaId: null,
    unidadBase: 'unidad',
    alicuotaId: ALICUOTA_ID,
    presentaciones: [
      { nombre: 'Unidad', unidadesBase: 1, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
    ],
    ...overrides,
  }
}

describe('esquemaProducto (tarea 10.3)', () => {
  it('acepta un producto con datos completos y una única referencia usada en venta', () => {
    const resultado = esquemaProducto.safeParse(productoValido())
    expect(resultado.success).toBe(true)
  })

  it('acepta varias presentaciones con exactamente una de referencia', () => {
    const resultado = esquemaProducto.safeParse(
      productoValido({
        presentaciones: [
          { nombre: 'Unidad', unidadesBase: 1, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
          { nombre: 'Pack x6', unidadesBase: 6, usarEnVenta: true, usarEnCompra: true, esReferencia: false },
        ],
      }),
    )
    expect(resultado.success).toBe(true)
  })

  describe('campos obligatorios', () => {
    it('rechaza un código vacío', () => {
      const resultado = esquemaProducto.safeParse(productoValido({ codigo: '   ' }))
      expect(resultado.success).toBe(false)
    })

    it('rechaza un nombre vacío', () => {
      const resultado = esquemaProducto.safeParse(productoValido({ nombre: '' }))
      expect(resultado.success).toBe(false)
    })

    it('rechaza una categoría con id inválido', () => {
      const resultado = esquemaProducto.safeParse(productoValido({ categoriaId: 'no-es-un-uuid' }))
      expect(resultado.success).toBe(false)
    })
  })

  describe('unidades base enteras >= 1 (INV-04)', () => {
    it('acepta unidadesBase = 1', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: 1, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
          ],
        }),
      )
      expect(resultado.success).toBe(true)
    })

    it('rechaza unidadesBase = 0', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: 0, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
          ],
        }),
      )
      expect(resultado.success).toBe(false)
    })

    it('rechaza unidadesBase fraccionario', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: 1.5, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
          ],
        }),
      )
      expect(resultado.success).toBe(false)
    })

    it('rechaza unidadesBase negativo', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: -3, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
          ],
        }),
      )
      expect(resultado.success).toBe(false)
    })
  })

  describe('al menos una presentación (CAT-02)', () => {
    it('rechaza un producto sin presentaciones', () => {
      const resultado = esquemaProducto.safeParse(productoValido({ presentaciones: [] }))
      expect(resultado.success).toBe(false)
    })
  })

  describe('exactamente una referencia con venta (CAT-03)', () => {
    it('rechaza cuando ninguna presentación es de referencia', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: 1, usarEnVenta: true, usarEnCompra: false, esReferencia: false },
          ],
        }),
      )
      expect(resultado.success).toBe(false)
    })

    it('rechaza cuando hay más de una presentación de referencia', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: 1, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
            { nombre: 'Pack x6', unidadesBase: 6, usarEnVenta: true, usarEnCompra: false, esReferencia: true },
          ],
        }),
      )
      expect(resultado.success).toBe(false)
    })

    it('rechaza cuando la referencia no se usa en venta', () => {
      const resultado = esquemaProducto.safeParse(
        productoValido({
          presentaciones: [
            { nombre: 'Unidad', unidadesBase: 1, usarEnVenta: false, usarEnCompra: true, esReferencia: true },
          ],
        }),
      )
      expect(resultado.success).toBe(false)
    })
  })
})
