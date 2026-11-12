/**
 * Change 13, tarea 12.1: esquemas Zod de las pantallas de listas de precios. Solo UX: el
 * servidor valida igual (`MARGEN_INVALIDO`, `REDONDEO_INVALIDO`, `VIGENCIA_INVALIDA`,
 * `IMPORTE_INVALIDO`, `ALCANCE_INVALIDO`). Nada se convierte a `number` (INV-03).
 */

import { describe, expect, it } from 'vitest'

import { esquemaLista, esquemaRedondeoCategoria } from '../../../../src/domain/precios/listaSchema'
import { esquemaPrecioManual, precioParaApi } from '../../../../src/domain/precios/precioManualSchema'
import {
  construirVigencia,
  crearEsquemaDePublicacion,
} from '../../../../src/domain/precios/publicacionSchema'
import {
  esquemaRegla,
  fraccionDesdePorcentaje,
  porcentajeDesdeFraccion,
} from '../../../../src/domain/precios/reglaSchema'

const CATEGORIA = '11111111-1111-4111-8111-111111111111'

describe('esquemaLista (PRC-01, D9)', () => {
  const base = { nombre: 'General', redondeo_multiplo: '100', redondeo_direccion: 'ARRIBA' }

  it.each(['100', '0.01', '0,5', '2.50', '1000'])('acepta el múltiplo %s', (multiplo) => {
    expect(esquemaLista.safeParse({ ...base, redondeo_multiplo: multiplo }).success).toBe(true)
  })

  it.each(['0', '0.00', '-5', '1.005', 'abc', '', '1e3'])('rechaza el múltiplo %s', (multiplo) => {
    const resultado = esquemaLista.safeParse({ ...base, redondeo_multiplo: multiplo })

    expect(resultado.success).toBe(false)
    expect(resultado.error?.issues[0]?.path).toEqual(['redondeo_multiplo'])
  })

  it('normaliza la coma decimal a punto, sin pasar por number', () => {
    const resultado = esquemaLista.parse({ ...base, redondeo_multiplo: '0,5' })

    expect(resultado.redondeo_multiplo).toBe('0.5')
  })

  it.each(['ARRIBA', 'CERCANO', 'ABAJO'])('acepta la dirección %s', (direccion) => {
    expect(esquemaLista.safeParse({ ...base, redondeo_direccion: direccion }).success).toBe(true)
  })

  it('rechaza una dirección fuera del catálogo y un nombre vacío', () => {
    expect(esquemaLista.safeParse({ ...base, redondeo_direccion: 'HACIA_ABAJO' }).success).toBe(false)
    expect(esquemaLista.safeParse({ ...base, nombre: '   ' }).success).toBe(false)
  })
})

describe('esquemaRedondeoCategoria (PRC-14)', () => {
  it('exige categoría, múltiplo positivo y dirección', () => {
    expect(
      esquemaRedondeoCategoria.safeParse({ categoria_id: CATEGORIA, multiplo: '50', direccion: 'CERCANO' }).success,
    ).toBe(true)
    expect(
      esquemaRedondeoCategoria.safeParse({ categoria_id: '', multiplo: '50', direccion: 'CERCANO' }).success,
    ).toBe(false)
    expect(
      esquemaRedondeoCategoria.safeParse({ categoria_id: CATEGORIA, multiplo: '0', direccion: 'CERCANO' }).success,
    ).toBe(false)
  })
})

describe('esquemaRegla (PRC-12, PRC-13, D8)', () => {
  const base = { tipo: 'MARKUP', porcentaje: '30', alcance_tipo: 'LISTA', alcance_id: '' }

  it('un margen bruto de 100% o más es inválido, un markup de 100% o más no', () => {
    const margen = esquemaRegla.safeParse({ ...base, tipo: 'MARGEN_BRUTO', porcentaje: '100' })

    expect(margen.success).toBe(false)
    expect(margen.error?.issues[0]?.path).toEqual(['porcentaje'])
    expect(esquemaRegla.safeParse({ ...base, tipo: 'MARGEN_BRUTO', porcentaje: '99.9999' }).success).toBe(true)
    expect(esquemaRegla.safeParse({ ...base, tipo: 'MARKUP', porcentaje: '150' }).success).toBe(true)
  })

  it.each(['-1', 'abc', '', '30.00001'])('rechaza el porcentaje %s', (porcentaje) => {
    expect(esquemaRegla.safeParse({ ...base, porcentaje }).success).toBe(false)
  })

  it('el alcance LISTA no lleva entidad y los demás la necesitan', () => {
    expect(esquemaRegla.safeParse({ ...base, alcance_tipo: 'LISTA', alcance_id: CATEGORIA }).success).toBe(false)
    const sinEntidad = esquemaRegla.safeParse({ ...base, alcance_tipo: 'CATEGORIA', alcance_id: '' })
    expect(sinEntidad.success).toBe(false)
    expect(sinEntidad.error?.issues[0]?.path).toEqual(['alcance_id'])
    expect(esquemaRegla.safeParse({ ...base, alcance_tipo: 'CATEGORIA', alcance_id: CATEGORIA }).success).toBe(true)
  })

  it('rechaza un alcance fuera del catálogo y un tipo desconocido', () => {
    expect(esquemaRegla.safeParse({ ...base, alcance_tipo: 'ZONA' }).success).toBe(false)
    expect(esquemaRegla.safeParse({ ...base, tipo: 'COMISION' }).success).toBe(false)
  })
})

describe('fraccionDesdePorcentaje / porcentajeDesdeFraccion (TR-02)', () => {
  it.each([
    ['30', '0.300000'],
    ['12,5', '0.125000'],
    ['0', '0.000000'],
    ['150', '1.500000'],
    ['33.3333', '0.333333'],
  ])('%s%% viaja como %s', (porcentaje, fraccion) => {
    expect(fraccionDesdePorcentaje(porcentaje)).toBe(fraccion)
  })

  it.each([
    ['0.300000', '30'],
    ['0.125000', '12.5'],
    ['1.500000', '150'],
    ['0.333333', '33.3333'],
  ])('la fracción %s se muestra como %s%%', (fraccion, porcentaje) => {
    expect(porcentajeDesdeFraccion(fraccion)).toBe(porcentaje)
  })

  it('va y vuelve sin perder dígitos', () => {
    expect(fraccionDesdePorcentaje(porcentajeDesdeFraccion('0.071429'))).toBe('0.071429')
  })
})

describe('esquemaPrecioManual (D7)', () => {
  it.each(['9000', '9000.5', '0.01', '9000,50'])('acepta %s', (precio) => {
    expect(esquemaPrecioManual.safeParse({ precio_final: precio }).success).toBe(true)
  })

  it.each(['0', '0.00', '-1', '10.999', 'abc', ''])('rechaza %s', (precio) => {
    expect(esquemaPrecioManual.safeParse({ precio_final: precio }).success).toBe(false)
  })

  it('normaliza la coma decimal', () => {
    expect(esquemaPrecioManual.parse({ precio_final: '9000,5' }).precio_final).toBe('9000.5')
  })
})

describe('precioParaApi', () => {
  it.each([
    ['9000', '9000.00'],
    ['9000,5', '9000.50'],
    ['1583.33', '1583.33'],
    ['0.1', '0.10'],
  ])('%s viaja como %s', (precio, esperado) => {
    expect(precioParaApi(precio)).toBe(esperado)
  })
})

describe('publicación (PRC-02, D6)', () => {
  const AHORA = new Date('2026-10-07T15:00:00Z')
  const esquema = crearEsquemaDePublicacion(AHORA)

  it('sin vigencias es válida: rige desde la publicación', () => {
    expect(esquema.safeParse({ vigencia_desde: '', vigencia_hasta: '' }).success).toBe(true)
  })

  it('la vigencia hasta debe ser posterior a la vigencia desde', () => {
    const igual = esquema.safeParse({ vigencia_desde: '2026-10-10T09:00', vigencia_hasta: '2026-10-10T09:00' })
    const antes = esquema.safeParse({ vigencia_desde: '2026-10-10T09:00', vigencia_hasta: '2026-10-09T09:00' })
    const despues = esquema.safeParse({ vigencia_desde: '2026-10-10T09:00', vigencia_hasta: '2026-11-01T09:00' })

    expect(igual.success).toBe(false)
    expect(antes.success).toBe(false)
    expect(antes.error?.issues[0]?.path).toEqual(['vigencia_hasta'])
    expect(despues.success).toBe(true)
  })

  it('sin vigencia desde, la hasta se compara con el momento de la publicación', () => {
    expect(esquema.safeParse({ vigencia_desde: '', vigencia_hasta: '2026-10-01T00:00' }).success).toBe(false)
    expect(esquema.safeParse({ vigencia_desde: '', vigencia_hasta: '2026-12-01T00:00' }).success).toBe(true)
  })

  it('construirVigencia convierte lo cargado a instantes con zona o a null', () => {
    expect(construirVigencia({ vigencia_desde: '', vigencia_hasta: '' })).toEqual({
      vigencia_desde: null,
      vigencia_hasta: null,
    })
    const vigencia = construirVigencia({ vigencia_desde: '2026-10-10T09:00', vigencia_hasta: '' })
    expect(vigencia.vigencia_hasta).toBeNull()
    expect(vigencia.vigencia_desde).toMatch(/^2026-10-10T\d\d:00:00\.000Z$/)
  })
})
